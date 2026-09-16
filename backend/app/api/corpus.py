from fastapi import APIRouter

from app.api.models import ApiModel
from app.auth.dependencies import CurrentUserDep
from app.database import documents
from app.database.session import SessionDep

router = APIRouter(prefix="/corpus", tags=["corpus"])


class CorpusCompanyOut(ApiModel):
    ticker: str
    company_name: str
    fiscal_years: list[int]


@router.get("")
async def list_corpus(_user: CurrentUserDep, session: SessionDep) -> list[CorpusCompanyOut]:
    """The companies and fiscal years a question can be about. The chat's empty state shows this."""
    return [
        CorpusCompanyOut(ticker=c.ticker, company_name=c.company_name, fiscal_years=list(c.fiscal_years))
        for c in await documents.corpus_overview(session)
    ]
