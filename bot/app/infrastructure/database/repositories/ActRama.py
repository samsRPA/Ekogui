from datetime import datetime

class ActRama():
    def __init__(self, table):
        self._table = table
    
    async def checkActExist(self, conn, radication:str, ntfDate:datetime, actRama :str, antRama:str):
        try:
            query = f"""
                SELECT 
                    1
                FROM 
                    {self._table} 
                WHERE
                    RADICADO_RAMA  =:radication
                AND
                    FECHA_ACTUACION  = :ntfDate
                AND 
                    ACTUACION_RAMA = :actRama
                AND (
                        (ANOTACION_RAMA IS NULL AND :antRama IS NULL)
                        OR TRIM(ANOTACION_RAMA) = TRIM(:antRama)
                    )
                AND 
                    ORIGEN_DATOS = :origin
                AND 
                    ROWNUM = 1
            """
            async with conn.cursor() as cursor:
                await cursor.execute(query, {
                    "radication": radication,
                    "ntfDate": ntfDate,
                    "actRama":actRama,
                    "antRama": antRama if antRama else None,
                    "origin":"EKOGUI"
                })
                row = await cursor.fetchone()
                return row is not None
        except Exception as e:
            raise RuntimeError(f"Error en insert de check de auto {e}")
        