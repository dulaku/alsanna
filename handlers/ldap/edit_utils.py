###############################################################################
# Some text formatting utilities useful for formatting messages that make sense 
# to encode as JSON for hand-editing.
###############################################################################


def find_separator(line):
    in_token = False
    escaped = False
    for i, c in enumerate(line):
        if (c == '"' or c == "'") and not escaped:
            in_token = False if in_token else True
            continue
        # This next bit does not handle escaping in JSON generally and it doesn't handle
        # invalid escape sequences, but it handles the specific case we care about - a
        # string containing a literal quote or a literal :. Since we only want to return
        # early on a : outside a string, and it can't be escaped outside a string, we
        # only need to keep track of "are we inside a string" and we only need to do
        # enough escaping to make sure we track that accurately.
        if c == '\\' and not escaped and in_token:
            escaped = True
            continue
        if c == ':' and not in_token:
            return i
        if escaped:
            escaped = False
    return None


def raw_to_editable_mangle(json_doc, args):
    """
    Convert a JSON document in the intermediary format that stores metadata as part of
    each key or value in the document into one that visually separates the metadata
    for easy editing.
    """
    pre_formatted = []

    # Identify lines that have a : separator between a key and possibly value
    for line in json_doc.splitlines():
        split = find_separator(line)
        if split is None:
            pre_formatted.append(line)
        else:
            pre_formatted.append([line[:split], line[split + 2:]])  # Skip the ': '

    formatted = []
    left_padding = 0
    right_padding = args.ldap_min_width
    right_metadata = []

    # Compute left-padding preceding metadata strings
    for line in pre_formatted:
        if isinstance(line, list):  # We found a ':' separator in preformatting
            metadata_len = len(line[0].split('~')[0].split('"', maxsplit=1)[1])
            if metadata_len > left_padding:
                left_padding = metadata_len

    # Start constructing the lines of mangled JSON. Put in all the JSON but not the
    # right-padding between the end of the content and the rightward metadata, and
    # store that metadata for later use when we add the right-padding.
    for line in pre_formatted:
        if isinstance(line, list): # There was a : on this line. Certainly a key, maybe a value.
            key_metadata, key_content = line[0].split('~', maxsplit=1)
            leading_characters, key_metadata = key_metadata.split('"', maxsplit=1)
            val_data = line[1].rsplit('#', maxsplit=1)
            if len(val_data) == 2:  # There was in fact a value here
                val_content, val_metadata = val_data[0], val_data[1]
                val_metadata, trailing_characters = val_metadata.rsplit('"', maxsplit=1)
                val_data = None
                right_metadata.append(val_metadata)
            else:  # It's just a structural } or ] with whitespace, put it back.
                val_data = val_data[0]
                right_metadata.append(None)
            leading_formatted = (' ' * (left_padding - len(key_metadata))
                                 + key_metadata + ' | '
                                 + leading_characters + '"' + key_content
                                 + ': ' + ((val_content + '"' + trailing_characters)
                                           if val_data is None else val_data))
            formatted.append(leading_formatted)
        else:  # There was no : on this line; certainly no key, maybe a value.
            elem_data = line.rsplit('#', maxsplit=1)
            if len(elem_data) == 2:  # There was in fact a value here
                elem_content, elem_metadata = elem_data[0], elem_data[1]
                elem_metadata, trailing_characters = elem_metadata.rsplit('"', maxsplit=1)
                right_metadata.append(elem_metadata)
                elem_data = None
            else:  # It's just a structural } or ] with whitespace, put it back.
                elem_data = elem_data[0]
                right_metadata.append(None)
            leading_format = (' ' * left_padding + ' | '
                              + ((elem_content + '"' + trailing_characters)
                                 if elem_data is None else elem_data))
            formatted.append(leading_format)
        # And while we're at it keep track of line length for right-padding
        if len(formatted[-1]) > right_padding and len(formatted[-1]) < args.ldap_max_width:
            right_padding = len(formatted[-1])

    # Now add the right-padding and the metadata
    for i, metadata in enumerate(right_metadata):
        formatted[i] = formatted[i] + ' ' * (right_padding - len(formatted[i])) \
                       + ' | ' + ('' if metadata is None else metadata)
    ldap_json = '\n'.join(formatted)
    return ldap_json

def editable_to_raw_mangle(json_doc):
    """
    Recover the intermediate format from an edited message. Assumes that the editor
    did not edit the JSON structure or add/remove '|' characters that were added in
    raw_to_editable_mangle().
    """
    raw_msg = []
    for line in json_doc.splitlines():
        key_metadata, remain = line.split('|', maxsplit=1)
        content, val_metadata = remain.rsplit('|', maxsplit=1)
        sep = find_separator(content)
        if sep is not None:
            key, val = content[:sep].lstrip(), content[sep + 2:].rstrip()
            leading_characters, key = key.split('"', maxsplit=1)
            key = leading_characters + '"' + key_metadata.strip() + '~' + key
            val_data = val.rsplit('"', maxsplit=1)
            if len(val_data) == 2:  # Not guaranteed to have a value on the same line as the separator, unlike the key
                val = val_data[0] + '#' + val_metadata.strip() + '"' + val_data[1]
            content = key + ": " + val
        elif '"' in content:  # If this isn't true, then it's just a ] or } structural character
            elem, trailing_characters = content.rsplit('"', maxsplit=1)
            content = elem + '#' + val_metadata.strip() + '"' + trailing_characters
        raw_msg.append(content)
    return raw_msg
