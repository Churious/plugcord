"""Plugcord custom exception definitions."""


class PlugcordError(Exception):
    """Base exception for all Plugcord framework errors."""


class ConfigurationError(PlugcordError):
    """Raised when configuration loading, validation, or access fails."""


class DatabaseError(PlugcordError):
    """Raised when database operations fail."""


class PermissionDeniedError(PlugcordError):
    """Raised when a user attempts to execute a command without sufficient permissions."""

    def __init__(self, message: str = "You do not have permission to execute this command."):
        super().__init__(message)


class CommandConflictError(PlugcordError):
    """Raised when a command name or alias conflicts with an existing registered command."""

    def __init__(self, command_name: str, conflicting_module: str, current_module: str):
        self.command_name = command_name
        self.conflicting_module = conflicting_module
        self.current_module = current_module
        message = (
            f"Command or alias '{command_name}' from module '{current_module}' conflicts with "
            f"already registered command in module '{conflicting_module}'."
        )
        super().__init__(message)


class CommandRegistrationError(PlugcordError):
    """Raised when a command fails to register with the command registry."""


class ModuleError(PlugcordError):
    """Base exception for all module-related errors."""

    def __init__(self, module_id: str, message: str):
        self.module_id = module_id
        super().__init__(f"[{module_id}] {message}")


class PlugcordModuleNotFoundError(ModuleError):
    """Raised when a specified module is not found in the filesystem or registry."""

    def __init__(self, module_id: str):
        super().__init__(module_id, "Module not found.")


# Alias to satisfy requirements while avoiding shadowing built-in where desired
ModuleNotFoundError = PlugcordModuleNotFoundError


class ModuleAlreadyEnabledError(ModuleError):
    """Raised when attempting to enable an already enabled module."""

    def __init__(self, module_id: str):
        super().__init__(module_id, "Module is already enabled.")


class ModuleAlreadyDisabledError(ModuleError):
    """Raised when attempting to disable an already disabled module."""

    def __init__(self, module_id: str):
        super().__init__(module_id, "Module is already disabled.")


class InvalidManifestError(ModuleError):
    """Raised when a module manifest.json is missing, malformed, or invalid."""

    def __init__(self, module_id: str, details: str):
        self.details = details
        super().__init__(module_id, f"Invalid manifest: {details}")


class ModuleLoadError(ModuleError):
    """Raised when loading a module extension or cog fails."""

    def __init__(self, module_id: str, details: str):
        self.details = details
        super().__init__(module_id, f"Failed to load module: {details}")


class ModuleUnloadError(ModuleError):
    """Raised when unloading a module extension or cog fails."""

    def __init__(self, module_id: str, details: str):
        self.details = details
        super().__init__(module_id, f"Failed to unload module: {details}")


class ModuleReloadError(ModuleError):
    """Raised when reloading a module fails."""

    def __init__(self, module_id: str, details: str):
        self.details = details
        super().__init__(module_id, f"Failed to reload module: {details}")
