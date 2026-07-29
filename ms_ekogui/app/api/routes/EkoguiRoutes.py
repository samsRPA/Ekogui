from fastapi import APIRouter, Depends, HTTPException, status
from dependency_injector.wiring import inject, Provide

from app.dependencies.Dependencies import Dependencies
from app.api.dto.KeyRequestDto import KeyRequestDto
from app.api.dto.KeyResponseDto import KeyResponseDto
from app.api.dto.SearchCaseNumberRequestDto import SearchCaseNumberRequestDto
from app.domain.interfaces.IEkoguiService import IEkoguiService

router = APIRouter(
    prefix="/ekogui"
)


@router.post(
    "/allWithScraper",
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=KeyResponseDto,
    summary="Publicar todos los procesos de Ekogui filtrados por entidad y estado",
)
@inject
async def allWithScraper(
    request: KeyRequestDto,
    ekoguiService: IEkoguiService = Depends(Provide[Dependencies.ekoguiService]),
):
    try:
        resultado = await ekoguiService.publishOrder(
            request.entidades,
            request.estado,
            request.batchSize,
        )
        return KeyResponseDto.fromResultado(resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/searchCaseNumber",
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=KeyResponseDto,
    summary="Buscar y publicar un radicado puntual de una entidad",
)
@inject
async def searchCaseNumber(
    request: SearchCaseNumberRequestDto,
    ekoguiService: IEkoguiService = Depends(Provide[Dependencies.ekoguiService]),
):
    try:
        resultado = await ekoguiService.searchCaseNumber(
            request.entidadId,
            request.radicado,
            request.estado,
        )
        return KeyResponseDto.fromResultado(resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
