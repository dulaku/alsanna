import ssl
import os, subprocess, uuid
import argparse

class Handler:
    def __init__(self, arg_parser, remaining_args, final):
        self.arg_parser = argparse.ArgumentParser(parents=[arg_parser], 
                                                  add_help=final,
                                                  allow_abbrev=False)
        self.arg_parser.add_argument(
            "--client_cert", type=str, default=None,
            help="A client certificate to be used in negotiating TLS "
                 "connections. If supplied, alsanna will still not bother "
                 "validating any certificate presented by the client, but will "
                 "use this with the key supplied in --client_key to negotiate an "
                 "mTLS connection. Both this and --client_key must be supplied "
                 "or this has no effect."
        )
        self.arg_parser.add_argument(
            "--client_key", type=str, default=None,
            help="The private key corresponding to --client_cert. Has no effect "
                 "if --client_cert is not supplied."
        )
        self.arg_parser.add_argument(
            "--static_servername", action="store_true", 
            help="If supplied, --server_cert and --server_key are used as-is in "
                 "negotiating TLS connections. Otherwise (by default), alsanna "
                 "inspects the TLS handshake; if the client specifies an "
                 "expected host (SNI), that hostname is used, otherwise "
                 "--server_name is used in the certificate."
        )
        self.arg_parser.add_argument(
            "--server_name", type=str, default="example.com",
            help="Default server name to use when dynamically generating leaf "
                 "certificates and the client does not use SNI to indicate the "
                 "server name it expects."
        )
        self.arg_parser.add_argument(
            "--serv_cert", type=str, default="./tls_cert.pem",
            help="Path to a TLS certificate trusted by the software that "
                 "produces your traffic."
        )
        self.arg_parser.add_argument(
            "--serv_key", type=str, default="./tls_key.pem",
            help="Path to the private key corresponding to --serv_cert."
        )
        self.args, self.remaining_args = self.arg_parser.parse_known_args()

        self.retry_errors = [ssl.SSLWantReadError, ssl.SSLWantWriteError]
        self.servname = self.args.server_name # TODO: put in cnxn_locals instead
        self.static_servername = self.args.static_servername
        self.serv_cert = self.args.serv_cert
        self.serv_key = self.args.serv_key
        self.client_cert = self.args.client_cert
        self.client_key = self.args.client_key

        self.cert_dir = os.path.join(
          os.path.abspath(os.path.dirname(__file__)), # This file's location
          "certs"
        )
        if not os.path.isdir(self.cert_dir):
            os.mkdir(self.cert_dir)

        # Considerable elements borrowed from
        # https://gist.github.com/toolness/3073310
        self.key_size = 4096  # Should be >= 2048 or new OpenSSL versions grumble
        self.days_valid = 90  # It's on you to rotate your certs every 90 days
    
        self.openssl_template = (
            "prompt = no\r\n"
            "distinguished_name = req_distinguished_name\r\n"
            "req_extensions = v3_req\r\n"
            "\r\n"
            "[ req_distinguished_name ]\r\n"
            "CN = {0}\r\n"
            "\r\n"
            "[ v3_req ]\r\n"
            "basicConstraints = CA:FALSE\r\n"  # Leaf can't be CA
            "keyUsage = nonRepudiation, digitalSignature, keyEncipherment\r\n"
            "subjectAltName = @alt_names\r\n"
            "\r\n"
            "[ alt_names ]\r\n"
            "DNS.1 = {0}\r\n"
            "DNS.2 = *.{0}\r\n"
        )

    def setup_listener(self, listen_sock, cnxn_locals):
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.verify_mode = ssl.CERT_NONE
        if self.static_servername:
            tls_context.load_cert_chain(self.serv_cert, self.serv_key)
        else:
            tls_context.set_servername_callback(
                self.leaf_sign  # I literally cannot believe this worked
            )
        listen_sock = tls_context.wrap_socket(listen_sock,
                                              server_side=True)
        return listen_sock

    def setup_sender(self, send_sock, cnxn_locals):
        # Core alsanna logic ensures this is only ever called after negotiating
        # the client handshake, which is why we can assume self.servname is
        # already set by leaf_sign() if it needed to be.
        tls_context = ssl._create_unverified_context()
        if self.client_cert is not None and self.client_key is not None:
            tls_context.verify_mode = ssl.CERT_OPTIONAL
            tls_context.load_cert_chain(certfile=self.client_cert,
                                        keyfile=self.client_key)
        tls_context.check_hostname = False
        send_sock = tls_context.wrap_socket(
                        send_sock,
                        server_hostname=self.servname
                    )
        return send_sock

    def leaf_sign(self, ssl_sock, intended_server_name, ssl_context):
        self.servname = intended_server_name if intended_server_name is not None else self.servname

        dom_dir = os.path.join(self.cert_dir, self.servname)
        if not os.path.isdir(dom_dir):
            os.mkdir(dom_dir)
    
        conf_path = os.path.join(dom_dir, self.servname + ".conf")
        leaf_cert = os.path.join(dom_dir, self.servname + ".cert")
        leaf_key = os.path.join(dom_dir, self.servname + ".key")
        sign_req_path = os.path.join(dom_dir, self.servname + ".req")

        if not os.path.isfile(leaf_cert) or not os.path.isfile(leaf_key):
            with open(conf_path, "w") as conffile:
                conffile.write(self.openssl_template.format(self.servname))
            # Generate key
            subprocess.check_output(
                ['openssl', 'genrsa', '-out', leaf_key, str(self.key_size)],
                stderr=subprocess.DEVNULL
            )
            # Generate cert signing request
            subprocess.check_output(
                ['openssl', 'req', '-new', '-key', leaf_key, '-out',
                 sign_req_path, '-config', conf_path],
                stderr=subprocess.DEVNULL
            )
                # Generate cert
            subprocess.check_output(
                ['openssl', 'x509', '-req', '-days', str(self.days_valid),
                 '-in', sign_req_path, '-CA', self.serv_cert, '-CAkey', 
                 self.serv_key, '-set_serial', str(uuid.uuid4().int), 
                 '-out', leaf_cert, '-extensions', 'v3_req', '-extfile', 
                 conf_path],
                stderr=subprocess.DEVNULL
            )
        new_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        new_context.verify_mode = ssl.CERT_NONE
        new_context.load_cert_chain(leaf_cert, leaf_key)
        ssl_sock.context = new_context

    # Haven't implemented dissection of TLS as a protocol, just relying on
    # Python. For cases like this, where you haven't actually got a way of
    # displaying messages, this is the way to handle attempts to use it as the
    # final handler in a chain.
    def bytes_to_message(self, bytes):
        raise NotImplementedError # Don't use tls as the final handler

    def message_to_bytes(self, message):
        raise NotImplementedError # Don't use tls as the final handler
