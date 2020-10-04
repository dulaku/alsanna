import ssl
import os, subprocess, uuid

# Considerable elements borrowed from
# https://gist.github.com/toolness/3073310

def leaf_sign(ca_cert, ca_key, default_hostname):
    cert_dir = os.path.join(
      os.path.abspath(os.path.dirname(__file__)),
      "certs"
    )
    if not os.path.isdir(cert_dir):
        os.mkdir(cert_dir)

    key_size = 1024
    days_valid = 90  # Delete your certs every 90 days

    openssl_template = (
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

    def use_leaf_cert(ssl_sock, intended_server_name, ssl_context):
        if intended_server_name is None:
            intended_server_name = default_hostname

        dom_dir = os.path.join(cert_dir, intended_server_name)
        if not os.path.isdir(dom_dir):
            os.mkdir(dom_dir)

        conf_path = os.path.join(dom_dir, intended_server_name + ".conf")
        leaf_cert = os.path.join(dom_dir, intended_server_name + ".cert")
        leaf_key = os.path.join(dom_dir, intended_server_name + ".key")
        sign_req_path = os.path.join(dom_dir, intended_server_name + ".req")

        if not os.path.isfile(leaf_cert) or not os.path.isfile(leaf_key):
            with open(conf_path, "w") as conffile:
                conffile.write(openssl_template.format(intended_server_name))
            # Generate key
            subprocess.check_output(
                ['openssl', 'genrsa', '-out', leaf_key, str(key_size)]
            )
            # Generate cert signing request using cacert
            subprocess.check_output(
                ['openssl', 'req', '-new', '-key', leaf_key, '-out',
                 sign_req_path, '-config', conf_path]
            )
            # Generate cert
            subprocess.check_output(
                ['openssl', 'x509', '-req', '-days', str(days_valid),
                 '-in', sign_req_path, '-CA', ca_cert, '-CAkey', ca_key,
                 '-set_serial', str(uuid.uuid4().int), '-out', leaf_cert,
                 '-extensions', 'v3_req', '-extfile', conf_path]
            )
        new_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        new_context.load_cert_chain(leaf_cert, leaf_key)
        ssl_sock.context = new_context

    return use_leaf_cert
