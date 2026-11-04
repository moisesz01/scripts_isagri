import pyodbc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comun.db import cadena_conexion  # noqa: E402  (credenciales desde el .env)
from datetime import datetime


def conectar_sql_server():
    try:
        conn = pyodbc.connect(cadena_conexion())
        return conn
    except Exception as e:
        print(f"Error al conectar a SQL Server: {e}")
        return None

def migrar_datos_al():
    try:
        # Conectar a la base de datos
        conn = conectar_sql_server()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # Consulta para obtener registros con TypDoc='AK' (excluyendo el campo id)
        query_origen = """
        SELECT TypDoc, Socie, Exo, Ecri, NrLig, Dt, DtLiv, [Ref], Clien, Nr, Adres, AdrLiv, TiersLiv, 
               AdrFac, TiersFac, DtFac, DelRg, HtTtc, STva, PaysTx, DtEsc, RmqClient, MtHt, MtRDu, ZlAplha, 
               ZlListe, NbColis, NrExp, CommiVer, NrDeb, CommiDu, CoeffMn, TotalQtUni, MtHtRistourne, 
               MtTtcRistourne, EtatSync, Site, Deco, BaseCommi, DtDematerialisation, LieuTaxation, 
               RefFournFactRectif, Acti
        FROM docen_finanzas
        WHERE TypDoc = 'AL'
        """
        
        # Consulta para verificar si el registro ya existe en la tabla destino usando Nr
        query_verificar = """
        SELECT COUNT(*) 
        FROM encabezado_albaran_compras 
        WHERE Nr = ? AND TypDoc = ? AND Socie = ? AND Exo = ? AND Ecri = ? AND NrLig = ?
        """
        
        # Consulta para insertar en la tabla destino (sin el campo id)
        query_insertar = """
        INSERT INTO encabezado_albaran_compras (
            TypDoc, Socie, Exo, Ecri, NrLig, Dt, DtLiv, [Ref], Clien, Nr, Adres, AdrLiv, TiersLiv, 
            AdrFac, TiersFac, DtFac, DelRg, HtTtc, STva, PaysTx, DtEsc, RmqClient, MtHt, MtRDu, ZlAplha, 
            ZlListe, NbColis, NrExp, CommiVer, NrDeb, CommiDu, CoeffMn, TotalQtUni, MtHtRistourne, 
            MtTtcRistourne, EtatSync, Site, Deco, BaseCommi, DtDematerialisation, LieuTaxation, 
            RefFournFactRectif, Acti, numero_factura
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """
        
        # Obtener registros de origen
        cursor.execute(query_origen)
        registros = cursor.fetchall()
        
        total_registros = len(registros)
        registros_migrados = 0
        registros_duplicados = 0
        
        print(f"Iniciando migración de {total_registros} registros con TypDoc='AK'")
        
        for registro in registros:
            # Extraer campos clave para verificación (usando Nr en lugar de id)
            campos_clave = (registro.Nr, registro.TypDoc, registro.Socie, registro.Exo, registro.Ecri, registro.NrLig)
            
            # Verificar si el registro ya existe
            cursor.execute(query_verificar, campos_clave)
            existe = cursor.fetchone()[0] > 0
            
            if not existe:
                # Insertar registro en la tabla destino (excluyendo el campo id)
                cursor.execute(query_insertar, registro)
                registros_migrados += 1
            else:
                registros_duplicados += 1
        
        # Confirmar cambios
        conn.commit()
        
        print(f"Migración completada. Total registros: {total_registros}")
        print(f"Registros migrados: {registros_migrados}")
        print(f"Registros duplicados (no migrados): {registros_duplicados}")
        
        return True
        
    except Exception as e:
        print(f"Error durante la migración: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    inicio = datetime.now()
    print(f"Inicio del proceso: {inicio}")
    
    if migrar_datos_al():
        print("Proceso completado con éxito")
    else:
        print("Ocurrieron errores durante el proceso")
    
    fin = datetime.now()
    print(f"Fin del proceso: {fin}")
    print(f"Duración total: {fin - inicio}")
