from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def set_query_param(url: str, name: str, value: str) -> str:
    """
    Add or update a query parameter in a URL.

    Works with both absolute and relative URLs.
    If the parameter already exists, its value is replaced.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params[name] = [value]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def remove_query_param(url: str, name: str) -> str:
    """
    Remove a query parameter from a URL.

    Works with both absolute and relative URLs.
    If the parameter does not exist, the URL is returned unchanged.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop(name, None)
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
