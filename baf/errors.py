class InternalError(Exception):
    """An unexpected internal error that has not been handled."""
    pass


class BAFError(Exception):
    """The base error type for all non-internal BAF errors."""


class SpecError(BAFError):
    """An error in the user's datatype specification, such as if invalid
       arguments are passed."""
    pass


class BuildError(BAFError):
    """An error related to building, which may indicate the user has handled a
       datum in an unsupported way, e.g. building a non-instantiated model, or
       introducing cyclical dependencies."""
    pass


class ValidationError(BAFError):
    """An error indicating a datum has been passed invalid data to build.
       Usually occurs during preprocessing."""
    pass


class DependencyError(BAFError):
    """An error used to handle dependency resolution during the build of a
       Block. If any Datatype raises a DependencyError when accessed by a
       setter, it indicates that it first needs to be built before that setter
       can succeed. For example, attempting size() on a datum without a
       statically-known size will raise a DependencyError until the datum has
       been built."""
    pass

