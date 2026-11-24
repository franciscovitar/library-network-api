# Library Network — readiness de la demo pública

**Estado:** release de portfolio preparado; acceso público sin cuenta ni Basic Auth.  
**PR:** [#7](https://github.com/franciscovitar/library-network-api/pull/7).  
**Web:** https://library-network-qa-web.onrender.com/  
**API health:** https://library-network-qa-api.onrender.com/ready  
**Base:** Aiven PostgreSQL Free, únicamente con datos sintéticos.

## Alcance aprobado

- Publicar la interfaz para que reclutadores puedan usarla sin autenticarse.
- Conservar aislamiento automático por visitante, cookie HttpOnly, tokens de servicio firmados en el BFF, roles internos y operaciones transaccionales.
- Mantener ambos servicios Render Free y la instancia Aiven Free, sin gasto adicional, tarjetas, overages, recursos pagos o infraestructura adicional.
- No tocar Vercel, el proyecto library-network-showcase, Production ni datos de clientes/lectores.

## Pruebas de aceptación

- Abrir la web desde incógnito sin credenciales: raíz accesible y flujo de invitado sin solicitud de acceso.
- Iniciar una visita; catálogo y panel cargan desde PostgreSQL.
- Registrar préstamo y devolución; disponibilidad y préstamos activos cambian y persisten tras recarga.
- Abrir otra visita: espacio nuevo, sin leer ni modificar el anterior.
- Confirmar por registros que BFF→API es HTTPS y la API rechaza peticiones sin token de servicio.
- Revisar que la IP temporal del operador ya no está en la lista de acceso de Aiven.

Los resultados de cada verificación del commit final se documentan en la descripción del PR #7. El estado de la fusión a main se mantiene separado de la prueba/deploy de esta rama.

## Límites aceptados

Render Free asigna 750 horas de instancia por workspace compartidas entre servicios, duerme servicios tras 15 minutos inactivos, puede tardar alrededor de un minuto en arrancar y puede suspender servicios/builds al alcanzar cuotas si no existe método de pago. Cada instancia tiene 512 MB y filesystem efímero; no ofrece escala horizontal, disco persistente ni SLA.

Aiven Free limita la base a 1 CPU, 1 GB RAM, 1 GB de disco y 20 conexiones, no incluye pooler ni SLA y puede apagar la base si queda inactiva. No está destinada a datos reales ni operación empresarial.

La demo no configura WAF ni reglas externas de limitación por IP. Mantiene aislamiento, cookies firmadas, tokens internos, validación de origen y cuotas de producto para espacios y préstamos. Las identidades y todos los registros son ficticios. Los espacios vencen en 24 horas; la limpieza transaccional existe, pero el scheduler no está configurado y los registros expirados pueden ocupar disco hasta una limpieza manual.

## Estado de costo y seguridad

Verificado en las cuentas: planes Aiven/Render Free, US$0 adicional, sin método de pago agregado ni cargo automático habilitado. La API no acepta operaciones de navegador sin token BFF firmado; la clave de firma queda en el entorno secreto del servicio web. Solo el acceso al sitio de portfolio es público y sin contraseña.
