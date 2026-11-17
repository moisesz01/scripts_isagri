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
        
        
def migrar_datos():
    try:
        # Establecer conexión
        conn = pyodbc.connect(cadena_conexion())
        cursor = conn.cursor()

        # Consulta para obtener datos de la tabla origen
        query_origen = """
        SELECT DOCEN, TYPDOC, ARTIC, QTUNI, QT, UNITE, PUHT, TXREM, MTHT, PDUNITNET, 
               NBCOLIS, QTPARCOLIS, VOLUME, REPRE, DTFAC, CLIEN, DT, MTTTC, 
               MTTTCRISTOURNE, MTHTRISTOURNE, PUTTC, PUBASETTC, MARGE, PUBASEHT, 
               MtCommi, TxCommi
        FROM bodegaotazudb.dbo.docli_t
        WHERE TYPDOC='AK'
        """

        # Consulta para verificar existencia en tabla destino (con más campos)
        query_verificacion = """
        SELECT 1 
        FROM bodegaotazudb.dbo.detalle_pedido_compras
        WHERE DOCEN = ? AND TYPDOC = ? AND DT = ? AND ARTIC = ? AND QTUNI = ?
        """

        # Consulta para insertar en tabla destino
        query_insert = """
        INSERT INTO bodegaotazudb.dbo.detalle_pedido_compras
        (DOCEN, TYPDOC, ARTIC, QTUNI, QT, UNITE, PUHT, TXREM, MTHT, PDUNITNET, 
         NBCOLIS, QTPARCOLIS, VOLUME, REPRE, DTFAC, CLIEN, DT, MTTTC, 
         MTTTCRISTOURNE, MTHTRISTOURNE, PUTTC, PUBASETTC, MARGE, PUBASEHT, 
         MtCommi, TxCommi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Obtener datos de la tabla origen
        cursor.execute(query_origen)
        registros_origen = cursor.fetchall()

        # Contadores para estadísticas
        total_registros = 0
        registros_insertados = 0
        registros_duplicados = 0

        # Procesar cada registro
        for row in registros_origen:
            total_registros += 1
            
            # Verificar si el registro ya existe (con más campos)
            cursor.execute(query_verificacion, (
                row.DOCEN, 
                row.TYPDOC, 
                row.DT, 
                row.ARTIC, 
                row.QTUNI
            ))
            existe = cursor.fetchone()
            
            if not existe:
                # Insertar registro en tabla destino
                cursor.execute(query_insert, (
                    row.DOCEN,      # DOCEN
                    row.TYPDOC,     # TYPDOC
                    row.ARTIC,      # ARTIC
                    row.QTUNI,      # QTUNI
                    row.QT,         # QT
                    row.UNITE,      # UNITE
                    row.PUHT,       # PUHT
                    row.TXREM,      # TXREM
                    row.MTHT,       # MTHT
                    row.PDUNITNET,  # PDUNITNET
                    row.NBCOLIS,    # NBCOLIS
                    row.QTPARCOLIS, # QTPARCOLIS
                    row.VOLUME,     # VOLUME
                    row.REPRE,      # REPRE
                    row.DTFAC,      # DTFAC
                    row.CLIEN,      # CLIEN
                    row.DT,         # DT
                    row.MTTTC,      # MTTTC
                    row.MTTTCRISTOURNE,  # MTTTCRISTOURNE
                    row.MTHTRISTOURNE,  # MTHTRISTOURNE
                    row.PUTTC,      # PUTTC
                    row.PUBASETTC,  # PUBASETTC
                    row.MARGE,      # MARGE
                    row.PUBASEHT,   # PUBASEHT
                    row.MtCommi,    # MtCommi
                    row.TxCommi     # TxCommi
                ))
                registros_insertados += 1
            else:
                registros_duplicados += 1
                

        # Confirmar cambios
        conn.commit()
        today_date = date.today()
        execution_output = "Success"
        guardar_mensaje(f"Fecha de Ejecución: {today_date} | Estado Ejecución: {execution_output}\n")
        # Mostrar estadísticas detalladas
        print("\nResumen de la migración:")
        print(f"Total de registros procesados: {total_registros}")
        print(f"Registros insertados exitosamente: {registros_insertados}")
        print(f"Registros duplicados (omitidos): {registros_duplicados}")
        if total_registros:
            print(f"Porcentaje de nuevos registros: {registros_insertados/total_registros*100:.2f}%")

    except Exception as e:
        print(f"\nError durante la migración: {str(e)}")
        execution_output = e
        today_date = date.today()
        guardar_mensaje(f"Fecha de Ejecución: {today_date} | Estado Ejecución: {execution_output}\n")
        if 'conn' in locals():
            conn.rollback()
        # Propagar el error: Prefect marca la tarea como fallida y el
        # Programador de tareas recibe código de salida 1
        raise
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrar_datos()
