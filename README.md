# FreeDonna IMS

FreeDonna IMS es un sistema de gestión de inventario y ventas desarrollado con Django, pensado para cubrir el flujo real de un local (por ejemplo, indumentaria), donde necesitás controlar stock, vender rápido y tener registro claro de todo lo que pasa.

Desde el sistema se pueden cargar y administrar productos con código de barras único, manejar precios y stock, y evitar inconsistencias típicas (como productos duplicados o stock negativo). Todo el inventario se actualiza automáticamente a medida que se venden o se devuelven productos.

El módulo de punto de venta (POS) permite armar ventas con múltiples ítems, aplicar descuentos y cerrar la operación en el momento. Cada venta queda registrada con su detalle, lo que permite después consultar histórico, auditar movimientos o generar reportes.

También está implementado el flujo de devoluciones, vinculado a una venta, que restaura el stock de forma automática sin necesidad de ajustes manuales. Esto evita errores y mantiene consistencia en los datos.

El sistema incluye control de caja y reportes diarios, con posibilidad de exportar resúmenes en PDF para tener una visión rápida de ventas, ingresos y movimientos del día.

Además, soporta múltiples locales, permitiendo separar la operación por sucursal y mantener organizado el manejo de productos, ventas y reportes según cada contexto.

En general, el foco del proyecto está en modelar correctamente las operaciones de negocio y mantener consistencia de stock en tiempo real, más que en lo visual.
