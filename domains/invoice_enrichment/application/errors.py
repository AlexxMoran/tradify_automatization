class InvoiceProcessingError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class ConfigurationError(InvoiceProcessingError):
    status_code = 503


class ExternalDependencyError(InvoiceProcessingError):
    status_code = 502


class ParsingError(InvoiceProcessingError):
    status_code = 422


class PdfCompositionError(InvoiceProcessingError):
    status_code = 500
