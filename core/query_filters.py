"""
Shared query-parameter helpers for list API views.
"""


def parse_status_query_param(request, status_choices):
    """
    Parse and validate an optional ``status`` query parameter.

    Args:
        request: DRF request with query_params.
        status_choices: Iterable of (value, label) tuples from model STATUS_CHOICES.

    Returns:
        tuple: (status_value, error_message)
            - (None, None) when the parameter is omitted.
            - (str, None) when valid.
            - (None, str) when invalid.
    """
    raw = request.query_params.get('status')
    if raw is None or str(raw).strip() == '':
        return None, None

    status_value = str(raw).strip().lower()
    valid_statuses = {choice[0] for choice in status_choices}
    if status_value not in valid_statuses:
        allowed = ', '.join(sorted(valid_statuses))
        return None, f"Invalid status '{raw}'. Allowed values: {allowed}"

    return status_value, None


def parse_search_query_param(request, param_name='search'):
    """
    Parse an optional case-insensitive search query parameter.

    Args:
        request: DRF request with query_params.
        param_name: Query string key (default: ``search``).

    Returns:
        str | None: Stripped search term, or None when omitted/blank.
    """
    raw = request.query_params.get(param_name)
    if raw is None:
        return None

    search_term = str(raw).strip()
    if not search_term:
        return None

    return search_term


def parse_boolean_query_param(request, param_name):
    """
    Parse an optional boolean query parameter.

    Args:
        request: DRF request with query_params.
        param_name: Query string key.

    Returns:
        tuple: (bool_value, error_message)
            - (None, None) when the parameter is omitted.
            - (bool, None) when valid.
            - (None, str) when invalid.
    """
    raw = request.query_params.get(param_name)
    if raw is None or str(raw).strip() == '':
        return None, None

    normalized = str(raw).strip().lower()
    if normalized in {'true', '1', 'yes'}:
        return True, None
    if normalized in {'false', '0', 'no'}:
        return False, None

    return None, f"Invalid {param_name} '{raw}'. Allowed values: true, false"
