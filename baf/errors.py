class BuildError(Exception):
    '''The base exception class used for all errors handled during the BAF
    build process.'''
    pass


class DataMissingError(BuildError):
    '''An exception class used when BAF fails to fetch data from a `Block`,
    `Array`, or other datatype that has not yet been fully built.'''
    pass


class ValidationError(BuildError):
    '''An exception class used when a datatype is provided data of the wrong
    type, or if the data provided is out of range.'''
    pass
