import pyodbc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comun.db import cadena_conexion  # noqa: E402  (credenciales desde el .env)
from datetime import datetime, timedelta


def actualizar_facturas_en_albaranes():
    conn = None
    try:
        # Establecer conexión usando las variables configuradas
        conn = pyodbc.connect(cadena_conexion())
        cursor = conn.cursor()

        # Calcular fecha límite (3 meses atrás desde hoy)
        fecha_limite = datetime.now() - timedelta(days=90)

        # 1. Consulta para obtener facturas (TYPDOC='AF') de los últimos 3 meses
        query_facturas = """
        SELECT DOCEN, ARTIC, QTUNI, QT, CLIEN, CONVERT(datetime, DT) as FechaDT
        FROM bodegaotazudb.dbo.docli_t
        WHERE TYPDOC='AF' 
          AND ARTIC NOT IN ('_C_','PORTES')
          AND CONVERT(datetime, DT) >= ?
        """

        # 2. Consulta para buscar albaranes coincidentes con los criterios especificados
        query_buscar_albaranes = """
        SELECT DOCEN, CONVERT(datetime, DT) as FechaAlbaran
        FROM bodegaotazudb.dbo.detalle_albaran_compras
        WHERE ARTIC = ? 
          AND QTUNI = ? 
          AND QT = ? 
          AND CLIEN = ? 
          AND numero_factura IS NULL
          AND ARTIC NOT IN ('_C_','PORTES')
          AND CONVERT(datetime, DT) BETWEEN ? AND ?
        """

        # 3. Consulta para verificar si el albarán ya está asignado a otra factura
        query_verificar_asignacion = """
        SELECT COUNT(*) 
        FROM bodegaotazudb.dbo.detalle_albaran_compras
        WHERE DOCEN = ? AND numero_factura IS NOT NULL
        """

        # 4. Consulta para actualizar albaranes
        query_actualizar_albaran = """
        UPDATE bodegaotazudb.dbo.detalle_albaran_compras
        SET numero_factura = ?
        WHERE DOCEN = ? AND ARTIC = ? AND numero_factura IS NULL
        """

        # Ejecutar consulta de facturas (solo las de los últimos 3 meses)
        cursor.execute(query_facturas, (fecha_limite,))
        facturas = cursor.fetchall()

        # Contadores para estadísticas
        total_facturas = len(facturas)
        albaranes_actualizados = 0
        sin_albaranes = 0
        multi_albaranes = 0
        albaranes_ya_asignados = 0

        for factura in facturas:
            fecha_factura = factura.FechaDT
            fecha_inicio = fecha_factura - timedelta(days=90)
            fecha_fin = fecha_factura + timedelta(days=90)
            
            # Buscar albaranes coincidentes
            cursor.execute(query_buscar_albaranes, (
                factura.ARTIC, 
                factura.QTUNI, 
                factura.QT, 
                factura.CLIEN,
                fecha_inicio,
                fecha_fin
            ))
            albaranes = cursor.fetchall()
            
            if not albaranes:
                sin_albaranes += 1
                continue
                
            # Filtrar albaranes no asignados
            albaranes_no_asignados = []
            for albaran in albaranes:
                cursor.execute(query_verificar_asignacion, (albaran.DOCEN,))
                if cursor.fetchone()[0] == 0:
                    albaranes_no_asignados.append(albaran)
                else:
                    albaranes_ya_asignados += 1
            
            if not albaranes_no_asignados:
                continue
                
            if len(albaranes_no_asignados) == 1:
                albaran_seleccionado = albaranes_no_asignados[0]
            else:
                # Múltiples coincidencias: seleccionar el más cercano en fecha
                albaran_seleccionado = min(
                    albaranes_no_asignados, 
                    key=lambda x: abs((x.FechaAlbaran - fecha_factura).days)
                )
                multi_albaranes += 1
            
            # Actualizar el albarán seleccionado
            cursor.execute(query_actualizar_albaran, (
                factura.DOCEN,
                albaran_seleccionado.DOCEN,
                factura.ARTIC  # Asegurar que solo actualizamos el mismo artículo
            ))
            albaranes_actualizados += 1

        # Confirmar transacción
        conn.commit()
        
        # Mostrar reporte final
        print("\n=== Reporte de Actualización ===")
        print(f"🔹 Total facturas procesadas (últimos 3 meses): {total_facturas}")
        print(f"✅ Albaranes actualizados: {albaranes_actualizados}")
        print(f"⚠️  Facturas sin albarán coincidente: {sin_albaranes}")
        print(f"🔀 Casos con múltiples albaranes: {multi_albaranes}")
        print(f"🚫 Albaranes ya asignados a otras facturas: {albaranes_ya_asignados}")
        if total_facturas > 0:
            print(f"📊 Tasa de éxito: {(albaranes_actualizados/total_facturas)*100:.1f}%")
        else:
            print("📊 No hay facturas para procesar en el período seleccionado")

    except Exception as e:
        print(f"\n❌ Error durante el proceso: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("\nConexión a la base de datos cerrada.")

if __name__ == "__main__":
    print("Iniciando proceso de actualización de facturas de los últimos 3 meses...")
    actualizar_facturas_en_albaranes()
