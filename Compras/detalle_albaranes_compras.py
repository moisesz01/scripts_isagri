import pyodbc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comun.db import cadena_conexion  # noqa: E402  (credenciales desde el .env)
from datetime import date



def guardar_mensaje(mensaje):
    # Obtiene la ruta absoluta del script que se está ejecutando
    ruta_absoluta = os.path.dirname(os.path.abspath(__file__))

    # Obtiene el directorio padre
    directorio_padre = os.path.dirname(ruta_absoluta)

    # Define la ruta del directorio de logs
    directorio_logs = os.path.join(directorio_padre, 'logs')

    # Si el directorio de logs no existe, lo crea
    if not os.path.exists(directorio_logs):
        os.makedirs(directorio_logs)

    # Define la ruta completa del archivo
    ruta_completa_archivo = os.path.join(directorio_logs, 'log_detalle_albaranes.txt')

    # Agrega el mensaje al final del archivo
    with open(ruta_completa_archivo, 'a') as archivo:
        archivo.write(mensaje + '\n')
        archivo.close()
        
def migrar_albaranes_compras():
    try:
        # Establecer conexión
        conn = pyodbc.connect(cadena_conexion())
        cursor = conn.cursor()

        # 1. Consulta para obtener albaranes de compra (TYPDOC='AL')
        query_albaranes = """
        SELECT DOCEN, TYPDOC, ARTIC, QTUNI, QT, UNITE, PUHT, TXREM, MTHT, PDUNITNET, 
               NBCOLIS, QTPARCOLIS, VOLUME, REPRE, DTFAC, CLIEN, DT, MTTTC, 
               MTTTCRISTOURNE, MTHTRISTOURNE, PUTTC, PUBASETTC, MARGE, PUBASEHT, 
               MtCommi, TxCommi
        FROM bodegaotazudb.dbo.docli_t
        WHERE TYPDOC='AL'
        """

        # 2. Consulta para verificar existencia en detalle_albaran_compras
        query_verificar_albaran = """
        SELECT 1 
        FROM bodegaotazudb.dbo.detalle_albaran_compras
        WHERE DOCEN = ? AND TYPDOC = ? AND ARTIC = ? AND QTUNI = ? AND CLIEN = ?
        """

        # 3. Consulta para buscar pedidos relacionados (con numero_albaran nulo)
        query_buscar_pedido = """
        SELECT DOCEN 
        FROM bodegaotazudb.dbo.detalle_pedido_compras
        WHERE ARTIC = ? AND QTUNI = ? AND QT = ? AND CLIEN = ? AND numero_albaran IS NULL
        """

        # 4. Consulta para actualizar pedido con número de albarán (sin DOCEN en WHERE)
        query_actualizar_pedido = """
        UPDATE bodegaotazudb.dbo.detalle_pedido_compras
        SET numero_albaran = ?
        WHERE ARTIC = ? AND QTUNI = ? AND QT = ? AND CLIEN = ? AND numero_albaran IS NULL
        """

        # 5. Consulta para insertar en detalle_albaran_compras
        query_insert_albaran = """
        INSERT INTO bodegaotazudb.dbo.detalle_albaran_compras
        (DOCEN, TYPDOC, ARTIC, QTUNI, QT, UNITE, PUHT, TXREM, MTHT, PDUNITNET, 
         NBCOLIS, QTPARCOLIS, VOLUME, REPRE, DTFAC, CLIEN, DT, MTTTC, 
         MTTTCRISTOURNE, MTHTRISTOURNE, PUTTC, PUBASETTC, MARGE, PUBASEHT, 
         MtCommi, TxCommi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Obtener albaranes de la tabla origen
        cursor.execute(query_albaranes)
        albaranes = cursor.fetchall()

        # Contadores para estadísticas
        total_albaranes = 0
        albaranes_insertados = 0
        albaranes_duplicados = 0
        pedidos_actualizados = 0

        for albaran in albaranes:
            total_albaranes += 1
            
            # Verificar si el albarán ya existe en detalle_albaran_compras
            cursor.execute(query_verificar_albaran, (
                albaran.DOCEN, 
                albaran.TYPDOC, 
                albaran.ARTIC, 
                albaran.QTUNI, 
                albaran.CLIEN
            ))
            existe_albaran = cursor.fetchone()
            
            if not existe_albaran:
                # Buscar pedidos relacionados para actualizar
                cursor.execute(query_buscar_pedido, (
                    albaran.ARTIC, 
                    albaran.QTUNI, 
                    albaran.QT, 
                    albaran.CLIEN
                ))
                pedidos_relacionados = cursor.fetchall()
                
                # Actualizar pedidos con el número de albarán (sin DOCEN en WHERE)
                if pedidos_relacionados:
                    cursor.execute(query_actualizar_pedido, (
                        albaran.DOCEN,  # numero_albaran
                        albaran.ARTIC, 
                        albaran.QTUNI, 
                        albaran.QT, 
                        albaran.CLIEN
                    ))
                    pedidos_actualizados += cursor.rowcount
                
                # Insertar el albarán en detalle_albaran_compras
                cursor.execute(query_insert_albaran, (
                    albaran.DOCEN,      # DOCEN
                    albaran.TYPDOC,     # TYPDOC
                    albaran.ARTIC,      # ARTIC
                    albaran.QTUNI,      # QTUNI
                    albaran.QT,         # QT
                    albaran.UNITE,      # UNITE
                    albaran.PUHT,       # PUHT
                    albaran.TXREM,      # TXREM
                    albaran.MTHT,      # MTHT
                    albaran.PDUNITNET,  # PDUNITNET
                    albaran.NBCOLIS,    # NBCOLIS
                    albaran.QTPARCOLIS, # QTPARCOLIS
                    albaran.VOLUME,     # VOLUME
                    albaran.REPRE,      # REPRE
                    albaran.DTFAC,      # DTFAC
                    albaran.CLIEN,      # CLIEN
                    albaran.DT,         # DT
                    albaran.MTTTC,      # MTTTC
                    albaran.MTTTCRISTOURNE,  # MTTTCRISTOURNE
                    albaran.MTHTRISTOURNE,  # MTHTRISTOURNE
                    albaran.PUTTC,      # PUTTC
                    albaran.PUBASETTC,  # PUBASETTC
                    albaran.MARGE,      # MARGE
                    albaran.PUBASEHT,   # PUBASEHT
                    albaran.MtCommi,    # MtCommi
                    albaran.TxCommi     # TxCommi
                ))
                albaranes_insertados += 1
            else:
                albaranes_duplicados += 1

        # Confirmar cambios
        conn.commit()
        
        # Mostrar estadísticas
        print("\nResumen de la migración de albaranes:")
        print(f"Total de albaranes procesados: {total_albaranes}")
        print(f"Albaranes insertados en detalle_albaran_compras: {albaranes_insertados}")
        print(f"Albaranes duplicados (omitidos): {albaranes_duplicados}")
        print(f"Pedidos actualizados con número de albarán: {pedidos_actualizados}")
        today_date = date.today()
        execution_output = "Success"
        guardar_mensaje(f"Fecha de Ejecución: {today_date} | Estado Ejecución: {execution_output}\n")

    except Exception as e:
        print(f"\nError durante la migración: {str(e)}")
        execution_output = e
        guardar_mensaje(f"Fecha de Ejecución: {today_date} | Estado Ejecución: {execution_output}\n")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrar_albaranes_compras()
