"""Exception handling utilities."""


def extract_all_exceptions(exception_group: ExceptionGroup) -> list[Exception]:
    """Extract all individual exceptions from an ExceptionGroup, including nested groups.

    Args:
        exception_group: The ExceptionGroup to extract exceptions from.

    Returns:
        A flat list of all individual exceptions contained in the group.

    """
    all_exceptions: list[Exception] = []

    for exception in exception_group.exceptions:
        if isinstance(exception, ExceptionGroup):
            # Recursively extract from nested ExceptionGroup
            all_exceptions.extend(extract_all_exceptions(exception))
        else:
            # Add individual exception
            all_exceptions.append(exception)

    return all_exceptions
