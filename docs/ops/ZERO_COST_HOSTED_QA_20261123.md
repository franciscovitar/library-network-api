# Library Network — alojamiento público de portfolio (US$0 adicional)

**Estado:** aplicación web pública, con acceso sin login y espacios de datos sintéticos aislados por visitante.  
**Fecha del despliegue QA base:** 2026-11-24. El recorrido de release final por HTTPS y navegador incógnito se registra en PR #7.  
**Código:** franciscovitar/library-network-api, PR #7, rama feat/library-network-zero-cost-qa-20261123.  
**URLs:** [web](https://library-network-qa-web.onrender.com/) · [API readiness](https://library-network-qa-api.onrender.com/ready).  
**Límite de gasto:** US$0 adicional; Aiven Free y Render Free; sin tarjeta, overages habilitados, recursos pagos, Neon ni cambios en Vercel/Production.

## Cómo funciona la demo

- Cualquiera abre la web y entra sin cuenta, contraseña, registro ni solicitud de acceso.
- La web BFF genera una identidad aleatoria por visita, guarda su capacidad en cookie HttpOnly y firma tokens de servicio. La clave privada y las credenciales permanecen en las variables secretas de Render.
- La API valida los tokens firmados. El visitante no elige su espacio, rol ni sucursal. Cada espacio recibe socios, sucursales, títulos y ejemplares sintéticos.
- Los préstamos y devoluciones usan la lógica transaccional del producto y persisten en Aiven PostgreSQL. Abrir otra visita crea otro espacio.
- La demo no acepta datos de bibliotecas o lectores reales.

## Recursos y costos

| Proveedor | Recurso | Nivel | Capacidad observada |
|---|---|---|---|
| Aiven | PostgreSQL library-network-qa-db | Free, US$0/mes | 1 CPU, 1 GB RAM, 1 GB almacenamiento, máximo 20 conexiones |
| Render | Web BFF library-network-qa-web | Free, US$0 | una instancia, 512 MB RAM |
| Render | API library-network-qa-api | Free, US$0 | una instancia, 512 MB RAM |

Ambos servicios Render y la base Aiven están en la región configurada para la demo; el acceso de la base se limita a los rangos de salida de Render. Las credenciales y secretos residen solo en Render. No se habilitaron otras bases, trabajadores, cron, discos, add-ons ni proveedores.

Las cuentas se revisaron antes de crear recursos: no se añadió un medio de pago ni se habilitaron cargos automáticos. Render indica que, sin medio de pago, agotar el ancho de banda incluido suspende servicios y agotar minutos de build pausa nuevos builds. No hay autorización para cambiar a un plan pago si eso ocurre.

## Límites gratuitos aceptados

### Render Free

- Cada workspace tiene 750 horas de instancia gratis por mes, compartidas por los servicios Free. Si se agotan, Render suspende las instancias Free hasta el mes siguiente.
- Un servicio Free se duerme luego de 15 minutos sin tráfico entrante y puede tardar cerca de un minuto en volver. La web y la API pueden arrancar en frío por separado.
- El build y la transferencia de salida tienen cuotas. Sin medio de pago, al alcanzar esos límites se suspenden servicios o nuevos builds; no se cambia automáticamente a un plan pago.
- Las instancias tienen 512 MB RAM, menos de 1 CPU, sistema de archivos efímero y una sola instancia. Render puede reiniciarlas; no hay disco persistente, shell, escalado horizontal ni caché edge en Free.

### Aiven PostgreSQL Free

- 1 CPU, 1 GB RAM, 1 GB de almacenamiento y 20 conexiones máximas; no incluye pooler ni SLA.
- No hay garantía de uptime. Aiven puede apagar servicios Free que permanezcan inactivos; se pueden encender nuevamente desde el panel.
- El espacio es pequeño: la demo usa únicamente datos sintéticos y el pool de API se limita a 2 conexiones base + 1 overflow por proceso.

### Limitaciones del producto/demo

- Los espacios invitados tienen vencimiento de 24 horas. Existe una limpieza transaccional, pero no hay un scheduler gratuito configurado; filas expiradas pueden permanecer en la base hasta una limpieza manual.
- No se agregó WAF ni limitación de tráfico por IP. Se mantienen los topes de creación y uso por espacio, las cookies firmadas, la validación de origen y el aislamiento de datos. Es una demo abierta de datos ficticios, no una plataforma de producción.
- Si la base queda inactiva o se alcanza una cuota de Render, la demo puede tardar en arrancar o quedar temporalmente suspendida. Son límites esperables de los planes gratis.

## Comprobaciones de release

PR #7 conserva el resultado de la prueba en navegador incógnito sin credenciales: entrada pública, creación aislada, lectura de catálogo, préstamo, devolución y aislamiento frente a una segunda visita. Los registros de Render corroboran las llamadas HTTPS y las respuestas del backend; las migraciones Alembic 0001–0005 se ejecutaron con el usuario migrador de QA. Los datos y tokens de visitantes no se publican en CI ni en GitHub.

## Referencias oficiales

- [Aiven PostgreSQL Free tier](https://aiven.io/docs/products/postgresql/concepts/pg-free-tier)
- [Render Free compute](https://render.com/docs/free)
- [Render FAQ: límites, facturación sin tarjeta y arranques en frío](https://render.com/docs/faq)
