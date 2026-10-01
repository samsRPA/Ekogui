from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from dependency_injector.wiring import inject, Provide

from app.dependencies.Dependencies import Dependencies
from app.api.dto.KeyRequestDto import KeyRequestDto, State
from app.api.dto.KeyResponseDto import KeyResponseDto
from app.api.dto.SearchCaseNumberRequestDto import SearchCaseNumberRequestDto
from app.api.dto.SearchCaseNumbersRequestDto import SearchCaseNumbersRequestDto
from app.api.dto.SearchCaseNumbersResponseDto import SearchCaseNumbersResponseDto
from app.api.dto.SearchCaseNumbersBulkRequestDto import SearchCaseNumbersBulkRequestDto
from app.api.dto.SearchCaseNumbersBulkResponseDto import SearchCaseNumbersBulkResponseDto
from app.domain.interfaces.IEkoguiService import IEkoguiService

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")

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
        result = await ekoguiService.publishOrder(
            request.entidades,
            request.estado,
            request.batchSize,
        )
        return KeyResponseDto.fromResult(result)
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
        result = await ekoguiService.searchCaseNumber(
            request.entidadId,
            request.radicado,
            request.estado,
        )
        return KeyResponseDto.fromResult(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/searchCaseNumbers",
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SearchCaseNumbersResponseDto,
    summary="Buscar y publicar un grupo de radicados de una entidad",
)
@inject
async def searchCaseNumbers(
    request: SearchCaseNumbersRequestDto,
    ekoguiService: IEkoguiService = Depends(Provide[Dependencies.ekoguiService]),
):
    try:
        result = await ekoguiService.searchCaseNumbers(
            request.entidadId,
            request.radicados,
            request.estado,
        )
        return SearchCaseNumbersResponseDto.fromResult(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/searchCaseNumbersBulk",
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SearchCaseNumbersBulkResponseDto,
    summary="Bulk search and publish of case numbers of an entity (one pass over the entity listing)",
)
@inject
async def searchCaseNumbersBulk(
    request: SearchCaseNumbersBulkRequestDto,
    ekoguiService: IEkoguiService = Depends(Provide[Dependencies.ekoguiService]),
):
    try:
        result = await ekoguiService.searchCaseNumbersBulk(
            request.entityId,
            request.caseNumbers,
            request.state,
            request.batchSize,
        )
        return SearchCaseNumbersBulkResponseDto.fromResult(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/searchCaseNumbersBulkExcel",
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SearchCaseNumbersBulkResponseDto,
    summary="Bulk search and publish of the case numbers in the first column of the first sheet of an .xlsx file",
)
@inject
async def searchCaseNumbersBulkExcel(
    file: UploadFile = File(description=".xlsx file; case numbers are read from the first column of the first sheet (header optional)."),
    entityId: int = Form(description="Id of the entity to search the case numbers in."),
    state: State = Form(default="PROCESO_ENTIDAD_ACTIVO", description="State of the processes to search."),
    batchSize: int = Form(default=10, ge=1, description="Number of processes per batch published to the queue."),
    ekoguiService: IEkoguiService = Depends(Provide[Dependencies.ekoguiService]),
):
    if not (file.filename or "").lower().endswith(EXCEL_EXTENSIONS):
        raise HTTPException(status_code=400, detail=f"Only {', '.join(EXCEL_EXTENSIONS)} files are supported")

    content = await file.read()
    try:
        result = await ekoguiService.searchCaseNumbersFromExcel(entityId, content, state, batchSize)
        return SearchCaseNumbersBulkResponseDto.fromResult(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
