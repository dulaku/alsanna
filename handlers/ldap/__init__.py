import argparse, ast, threading
import impacket.ldap.ldapasn1
from pyasn1.codec import ber as pyasn1_codec_ber
from pyasn1.codec.native.decoder import decode as pyasn1_codec_native_decode
import pyasn1.error
from impacket.ldap import ldapasn1
import pyasn1.type.univ
from . import edit_utils
import json
import collections

from .. import tls

def build_ldap_encoder(unprintable_storage):
    """
    Return a JSONEncoder class that stores information on object we know we can't print.
    Converts LDAP structures into Python equivalents which are understood by the
    pyasn1 native decoder. Needs to be a closure like this because built-in json doesn't
    support an argument that does this kind of storage.
    """
    class LDAPEncoder(json.JSONEncoder):
        def default(self, obj, iskey=False, path=None):
            if path is None:
                path = []
            if isinstance(obj, pyasn1.type.univ.OctetString) and not obj.isValue:
                unprintable_storage.append(path)                
                return None
            elif  isinstance(obj, impacket.ldap.ldapasn1.LDAPMessage) \
               or isinstance(obj, pyasn1.type.univ.Choice) \
               or isinstance(obj, impacket.ldap.ldapasn1.BindRequest) \
               or isinstance(obj, impacket.ldap.ldapasn1.BindResponse) \
               or isinstance(obj, impacket.ldap.ldapasn1.SearchRequest) \
               or isinstance(obj, impacket.ldap.ldapasn1.SearchResultEntry) \
               or isinstance(obj, impacket.ldap.ldapasn1.AttributeValueAssertion) \
               or isinstance(obj, impacket.ldap.ldapasn1.PartialAttribute) \
               or isinstance(obj, impacket.ldap.ldapasn1.SearchResultDone) \
               or isinstance(obj, impacket.ldap.ldapasn1.ExtendedRequest) \
               or isinstance(obj, impacket.ldap.ldapasn1.ExtendedResponse) \
               or isinstance(obj, dict) \
               or isinstance(obj, collections.OrderedDict):
                return {self.default(k, iskey=True, path=path): self.default(v, iskey=False, path=path + [k]) 
                        for k, v in obj.items()}
            elif  isinstance(obj, impacket.ldap.ldapasn1.Controls) \
               or isinstance(obj, impacket.ldap.ldapasn1.AttributeSelection) \
               or isinstance(obj, impacket.ldap.ldapasn1.Referral) \
               or isinstance(obj, impacket.ldap.ldapasn1.PartialAttributeList) \
               or isinstance(obj, impacket.ldap.ldapasn1.SearchResultReference) \
               or isinstance(obj, pyasn1.type.univ.SetOf) \
               or isinstance(obj, list) \
               or isinstance(obj, tuple):
                return [self.default(e, iskey=False, path=path + [i]) for i, e in enumerate(obj)]
            else:
                return merge_metadata(obj, iskey=iskey)
    return LDAPEncoder


def decode_ldap_primitive(element):
    """
    element is a tuple whose 1st value is the type of the object we're decoding, and
    second element is the content. We have an option for each type we know how to
    decode, even though a lot of them are identical - will make it easier to tweak
    each if needed for convenience, e.g. customized metadata.
    """
    if element[0] == 'impacket.ldap.ldapasn1.LDAPDN':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.MessageID':
        return int(element[1])
    elif element[0] == 'impacket.ldap.ldapasn1.ResultCode':
        return int(impacket.ldap.ldapasn1.ResultCode(value=element[1]))
    elif element[0] == 'impacket.ldap.ldapasn1.LDAPString':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.AttributeDescription':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.AssertionValue':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.Scope':
        return int(impacket.ldap.ldapasn1.Scope(value=element[1]))
    elif element[0] == 'impacket.ldap.ldapasn1.DerefAliases':
        return int(impacket.ldap.ldapasn1.DerefAliases(value=element[1]))
    elif element[0] == 'impacket.ldap.ldapasn1.AttributeValue':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.AttributeDescription':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.URI':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.LDAPOID':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'impacket.ldap.ldapasn1.UnbindRequest':
        return None
    elif element[0] == 'pyasn1.type.univ.OctetString':
        return ast.literal_eval("b'" + element[1] + "'")
    elif element[0] == 'pyasn1.type.univ.Integer':
        return int(element[1])
    elif element[0] == 'pyasn1.type.univ.Boolean':
        return False if element[1] == 'False' else True
    elif element[0] == 'str':
        return str(element[1])
    else:
        raise NotImplementedError(str(element))


def decode_ldap_structure(obj, descending=False):
    """
    The necessary hook for decoding a JSON document into a Python object understood by
    pyasn1's native decoder. Individual fields are handled in decode_ldap_primitive but
    the structure is here. descending is used because the JSON decoder only supports
    a hook for objects (dict-equivalents), not arrays (list-equivalents), so we need
    to manually decode arrays as we find them. But this hook is called on objects from
    the inside out, so an array that contained objects would have already had those
    objects handled by the time this hook was called on the object holding that list.
    So we don't descend into any objects inside a list we recursed into.
    """
    if isinstance(obj, dict) or isinstance(obj, collections.OrderedDict) and not descending:
        decoded = collections.OrderedDict()
        for k, v in obj.items():
            decode_key = decode_ldap_primitive(k.split('~', maxsplit=1))
            if isinstance(v, str):
                decoded[decode_key] = decode_ldap_primitive(list(reversed(v.rsplit('#', maxsplit=1))))
            elif isinstance(v, list):
                decoded[decode_key] = decode_ldap_structure(v, descending=True)
            else:
                decoded[decode_key] = v
    elif isinstance(obj, list) and descending:
        decoded = []
        for e in obj:
            if isinstance(e, str):
                decoded.append(decode_ldap_primitive(list(reversed(e.rsplit('#', maxsplit=1)))))
            else:
                decoded.append(e)
    else:
        raise ValueError(obj)
    return decoded


def merge_metadata(obj, iskey):
    """
    Store object metadata in a recoverable format in a string representation
    Key metadata stored to the left, value metadata to the right
    Get the string representation of the object, encode it as UTF-8 bytes
    for easier reading and some structural guarantees about encoding bytes
    then chop off the b'' for a nicer UI. This may need editing depending on the
    metadata you want to display or what string representation you want of the 
    objects the protocol handles - you need to be able to recover the original 
    object.
    """
    if iskey:
        return str(type(obj)).split("'")[1] + '~' + str(str(obj).encode('utf-8'))[2:-1]
    else:
        return str(str(obj).encode('utf-8'))[2:-1] + '#' + str(type(obj)).split("'")[1]


class Handler:
    def __init__(self, arg_parser, final):
        self.arg_parser = argparse.ArgumentParser(parents=[arg_parser],
                                                  add_help=final,
                                                  conflict_handler='resolve',
                                                  allow_abbrev=False)
        self.arg_parser.add_argument(
            "--ldap_max_width", type=int, default=120,
            help="Maximum line width to pad JSON display out to. Genuinely "
                 "longer lines still get displayed in full but won't add excess "
                 "padding to shorter lines."
        )
        self.arg_parser.add_argument(
            "--ldap_min_width", type=int, default=60,
            help="Minimum line width to pad JSON display out to."
        )

        # Manually merge the TLS handler options

        self.tls_handler = tls.Handler(self.arg_parser, final=False)
        self.arg_parser = self.tls_handler.arg_parser
        self.args, self.remaining_args = self.arg_parser.parse_known_args()


    def setup_client_facing(self, listen_sock, cnxn_locals):
        """
        See LDAPSocket below for implementation. No special actions for the listener.
        """
        return LDAPSocket(listen_sock, self.tls_handler)

    def setup_server_facing(self, send_sock, cnxn_locals):
        """
        See LDAPSocket below for implementation. No special actions for the sender.
        """
        return LDAPSocket(send_sock, self.tls_handler)

    def obj_to_printable(self, ldap_msg):
        """
        Convert an LDAPMessage into a human-readable string.
        """
        unprintable_paths = [] # Keep track of elements that can't be represented in JSON

        # Convert everything we _can_ represent in JSON to a string with its type and
        # any other metadata stored in that string for later recovery.
        ldap_json = json.dumps(ldap_msg,
                               cls=build_ldap_encoder(unprintable_paths),
                               indent=2)

        unprintable_state = {}
        for path in unprintable_paths:  # unprintable_paths was filled by json.dumps()
            unprintable = ldap_msg
            for step in path:
                unprintable = unprintable[step]
            unprintable_state[tuple(path)] = unprintable

        # Mangle that JSON document to be easily edited by visually separating the
        # metadata from the data. No longer actually valid JSON though.
        ldap_json = edit_utils.raw_to_editable_mangle(ldap_json, self.args)

        return ldap_json, unprintable_state

    def printable_to_obj(self, message, unprintable_state):
        """
        Convert a human-readable message back into a bytestring to be forwarded to
        the server.
        """
        json_msg = edit_utils.editable_to_raw_mangle(message)
        msg = json.loads('\n'.join(json_msg), object_hook=decode_ldap_structure)

        # We delete the schema and anything else that the LDAPMessage() spec
        # doesn't expect, at least if the user didn't stick anything in
        # themselves (if they do we try to keep it). Other code might use this
        # to add something unprintable back in.
        for unprintable_obj in unprintable_state.keys():
            present_step = msg
            for step in unprintable_obj[:-1]:
                present_step = present_step[step]
            if present_step[unprintable_obj[-1]] is None:
                del present_step[unprintable_obj[-1]]

        ldap_msg = pyasn1_codec_native_decode(msg, asn1Spec=ldapasn1.LDAPMessage())
        return ldap_msg

import ssl
class LDAPSocket():
    """
    Socket that recvs bytes and returns an LDAPMessage, and accepts LDAPMessages to
    convert them into bytes to send. Uses impacket and pyasn1 to do the decoding.
    """

    def __init__(self, sock, tls_handler):
        self.sock = sock  # Underlying transport
        self.recv_buf = b''  # Store unread bytes
        self.tls_handler = tls_handler
        self.send_lock = threading.Lock()
        self.recv_lock =  threading.Lock()

    def connect(self, target_tuple):
        self.sock.connect(target_tuple)

    def close(self):
        self.sock.close()

    def send(self, ldap_msg):
        bytestr = pyasn1_codec_ber.encoder.encode(ldap_msg)
        sent = 0
        while sent < len(bytestr):
            try:
                with self.send_lock:
                    sent += self.sock.send(bytestr)
            except ConnectionResetError:
                return sent

        if 'protocolOp' in ldap_msg \
           and 'extendedResp' in ldap_msg['protocolOp'] \
           and 'resultCode' in ldap_msg['protocolOp']['extendedResp'] \
           and 'responseName' in ldap_msg['protocolOp']['extendedResp'] \
           and str(ldap_msg['protocolOp']['extendedResp']['resultCode']) == 'success' \
           and str(ldap_msg['protocolOp']['extendedResp']['responseName']) == '1.3.6.1.4.1.1466.20037' \
           and not isinstance(self.sock, tls.TLSSock):
            with self.send_lock:
                self.sock = self.tls_handler.setup_client_facing(self.sock, cnxn_locals={})
            self.recv_lock.release()
        return sent

    def recv(self, num_bytes):
        while True:
            try:
                message, remaining = pyasn1_codec_ber.decoder.decode(self.recv_buf,
                                                                     asn1Spec=ldapasn1.LDAPMessage())
                break
            except pyasn1.error.SubstrateUnderrunError:
                recvd = len(self.recv_buf)
                try:
                    with self.recv_lock:
                        self.recv_buf += self.sock.recv(num_bytes)
                except ConnectionResetError:  # Socket is closed here, give up
                    return None
                if len(self.recv_buf) == recvd:  # Socket is closed here, too
                    return None
        self.recv_buf = remaining
        if 'protocolOp' in message \
           and 'extendedResp' in message['protocolOp'] \
           and 'resultCode' in message['protocolOp']['extendedResp'] \
           and 'responseName' in message['protocolOp']['extendedResp'] \
           and str(message['protocolOp']['extendedResp']['resultCode']) == 'success' \
           and str(message['protocolOp']['extendedResp']['responseName']) == '1.3.6.1.4.1.1466.20037' \
           and not isinstance(self.sock, tls.TLSSock):
            with self.send_lock:
                self.sock = self.tls_handler.setup_server_facing(self.sock, cnxn_locals={})
        if 'protocolOp' in message \
           and 'extendedReq' in message['protocolOp'] \
           and 'requestName' in message['protocolOp']['extendedReq'] \
           and str(message['protocolOp']['extendedReq']['requestName']) == '1.3.6.1.4.1.1466.20037' \
           and not isinstance(self.sock, tls.TLSSock):
            self.recv_lock.acquire()
        return message

