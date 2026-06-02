# ManWTool v1.0.5

## Mejoras principales

- updater endurecido para trabajar con releases y ZIPs validados
- correccion de transforms en lote para evitar aplicar cambios a seleccion completa por error
- base de licencias integrada en el addon
- servidor minimo de licencias incluido para pruebas y despliegue inicial
- soporte para modulo protegido compilable con Cython
- build de release desde este repositorio con `py build_addon.py`

## Cambios de producto

- la instalacion directa de updates queda desactivada por defecto
- se añade `Debug logging` para soporte
- se documenta el flujo de release y comercializacion

## Notas

- la activacion comercial requiere configurar `License Server`
- si compilas `manwtool_protected`, el ZIP de release lo incluira automaticamente
