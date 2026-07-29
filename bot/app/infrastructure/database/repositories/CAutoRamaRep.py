from datetime import datetime

_URL_AUTO_PART_EXPR = {
    "url": "SUBSTR(URL_AUTO, 1, INSTR(URL_AUTO, '|') - 1)",
   
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

