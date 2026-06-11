"""
Validador de rutas seguro para el motor AI.
Usa Path.resolve() para validar matemáticamente que un target esté dentro del workspace.
"""
from pathlib import Path


def validate_path(workspace: Path, target: Path) -> Path:
    """
    Valida que la ruta target esté estrictamente dentro del workspace.
    
    Usa Path.resolve() para obtener rutas absolutas y canónicas,
    resolviendo symlinks y partes relativas.
    
    Args:
        workspace: Ruta base del área de trabajo (debe ser un directorio).
        target: Ruta objetivo a validar.
        
    Returns:
        La ruta resuelta del target si está dentro del workspace.
        
    Raises:
        PermissionError: Si el target está fuera del workspace o intenta escapar.
    """
    # Obtener rutas absolutas y canónicas
    workspace_resolved = workspace.resolve()
    target_resolved = target.resolve()
    
    # Convertir a strings para comparación de prefijos
    # Asegurar que workspace termine con separador para evitar falsos positivos
    # Ejemplo: /workspace vs /workspace_evil
    workspace_str = str(workspace_resolved)
    target_str = str(target_resolved)
    
    # Verificar que target comienza con workspace
    # Usamos os.sep para asegurar comparación correcta de directorios
    if not target_str.startswith(workspace_str + '/') and target_str != workspace_str:
        # Verificación adicional: si workspace no tiene trailing slash, 
        # verificar que no sea un prefijo parcial de nombre de directorio
        if not target_str.startswith(workspace_str):
            raise PermissionError(
                f"Path traversal detected: {target} is outside workspace {workspace}"
            )
        
        # Caso donde target_str == workspace_str pero debería ser un archivo/subdir
        # o caso donde el nombre del workspace es prefijo de otro directorio
        if len(target_str) > len(workspace_str):
            # Verificar que el siguiente caracter sea un separador
            next_char = target_str[len(workspace_str)]
            if next_char != '/':
                raise PermissionError(
                    f"Path traversal detected: {target} is outside workspace {workspace}"
                )
    
    return target_resolved
