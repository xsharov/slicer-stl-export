def unescape_arguments(text):
    values = []
    index = 0
    while index < len(text):
        if text[index] == '"':
            index += 1
            buffer = []
            while text[index] != '"':
                if text[index] == "\\":
                    index += 1
                    buffer.append({"r": "\r", "n": "\n"}.get(text[index], text[index]))
                else:
                    buffer.append(text[index])
                index += 1
            index += 1
        else:
            end = text.find(";", index)
            end = len(text) if end < 0 else end
            buffer = list(text[index:end])
            index = end
        values.append("".join(buffer))
        if index < len(text):
            if text[index] != ";":
                raise ValueError(f"unexpected separator at {index}: {text[index:]!r}")
            index += 1
    return values
