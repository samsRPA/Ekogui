from datetime import datetime

_URL_AUTO_PART_EXPR = {
    "url": "SUBSTR(URL_AUTO, 1, INSTR(URL_AUTO, '|') - 1)",
    "hash": "SUBSTR(URL_AUTO, INSTR(URL_AUTO, '|') + 1)",
}


class CAutoRamaRep():
    def __init__(self, table):
        self._table=table

    async def _existsByUrlAutoPart(self, conn, ntfDate: datetime, radication: str, part: str, value: str, origin: str) -> bool:
        try:
            partExpr = _URL_AUTO_PART_EXPR[part]
            query = f"""
                SELECT
                    1
                FROM
                    {self._table}
                WHERE
                    FECHA_NOTIFICACION = :ntfDate
                AND
                    RADICACION = :radication
                AND
                    {partExpr} = :value
                AND
                    ORIGEN =:origin
                AND
                    ROWNUM = 1
            """
            async with conn.cursor() as cursor:
                await cursor.execute(query, {
                    "ntfDate": ntfDate,
                    "radication": radication,
                    "value": value,
                    "origin": origin
                })
                row = await cursor.fetchone()
                return row is not None
        except Exception as e:
            raise RuntimeError(f"Error en check de auto por {part} {e}")

    async def checkAutoExist(self, conn, ntfDate:datetime, radication:str, urlAuto:str, origin: str):
        return await self._existsByUrlAutoPart(conn, ntfDate, radication, "url", urlAuto, origin)

    async def existsByHash(self, conn, ntfDate: datetime, radication: str, fileHash: str, origin: str) -> bool:
        return await self._existsByUrlAutoPart(conn, ntfDate, radication, "hash", fileHash, origin)

    async def maxConsecutive(self, conn, ntfDate: datetime, radication: str, origin: str) -> int:
        try:
            query = f"""
                SELECT
                    NVL(MAX(CONSECUTIVO), 0) AS MAX_CONSECUTIVO
                FROM
                    {self._table}
                WHERE
                    FECHA_NOTIFICACION = :ntfDate
                AND RADICACION = :radication
                AND ORIGEN = :origin
            """
            async with conn.cursor() as cursor:
                await cursor.execute(query, {
                    "ntfDate": ntfDate,
                    "radication": radication,
                    "origin": origin
                })
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            raise RuntimeError(f"Error al consultar MAX(CONSECUTIVO): {e}")

    async def addAutoRecord(self, conn, ntfDate: datetime, radication: str, s3Path: str, autoUrl: str, consecutive:int, origin: str):
        try:
            query = f"""
                INSERT INTO {self._table}(
                    FECHA_NOTIFICACION,
                    RADICACION,
                    CONSECUTIVO,
                    RUTA_S3,
                    FECHA_CREACION,
                    URL_AUTO,
                    ESTADO_DESCARGA,
                    ORIGEN,
                    TIPO_DOCUMENTO
                ) VALUES (
                    :ntfDate,
                    :radication,
                    :consecutive,
                    :s3Path,
                    :currentTimestamp,
                    :autoUrl,
                    'SI',
                    :origin,
                    'pdf'
                )
            """
            async with conn.cursor() as cursor:
                await cursor.execute(query, {
                    "ntfDate": ntfDate,
                    "radication": radication,
                    "s3Path": s3Path,
                    "consecutive":consecutive,
                    "currentTimestamp": datetime.now(),
                    "autoUrl": autoUrl,
                    "origin": origin
                })
            return True
        except Exception as e:
            raise RuntimeError(f"Error en insert de auto {e}")
