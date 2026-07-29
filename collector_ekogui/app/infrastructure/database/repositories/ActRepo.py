import json

import oracledb

class ActRepo:
    def __init__(self, tipoCargue: str) -> None:
        self.tipoCargue = tipoCargue

    async def insertBatch(self, conn: oracledb.AsyncConnection, rows: list[dict]) -> str:
        try:
            async with conn.cursor() as cursor:
                payload = json.dumps(rows, ensure_ascii=False)
                mensaje = cursor.var(str)

                await cursor.execute(
                    """
                    BEGIN
                        LITI.INSERT_MASIVOS.CARGUE_MASIVO(
                            P_TIPO_CARGUE => :tipo,
                            P_CLOB        => :jsonData,
                            P_MESSAGE     => :mensaje
                        );
                    END;
                    """,
                    {
                        "tipo": self.tipoCargue,
                        "jsonData": payload,
                        "mensaje": mensaje,
                    },
                )
                return mensaje.getvalue()
        except Exception as e:
            raise RuntimeError(f"Error cargando el procedimiento en db: {e}")
