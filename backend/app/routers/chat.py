"""
Chat router — server-side proxy for the AI assistant.

Why this endpoint exists
------------------------
The browser used to call api.openai.com directly, authenticating with
`NEXT_PUBLIC_OPENAI_API_KEY`. Anything prefixed `NEXT_PUBLIC_` is inlined into the
JavaScript bundle at build time and shipped to every visitor, so the key was
readable in DevTools by anyone who loaded the page, and billable by anyone who
copied it.

The key now lives only in the backend process. The browser talks to this endpoint;
this endpoint talks to OpenAI. The key is never serialised into a response.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.services.ai_service import answer_question, AIServiceError

router = APIRouter(prefix="/api", tags=["AI Assistant"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    """
    Answer a question about a simulation's results.

    The simulation is loaded server-side from `simulation_id` rather than trusting
    a context blob from the client: the browser should not be able to dictate the
    facts the assistant reasons over.
    """
    try:
        reply, tool_calls = await answer_question(
            question=body.message,
            simulation_id=body.simulation_id,
            history=[m.model_dump() for m in body.history],
            db=db,
        )
        return ChatResponse(reply=reply, tool_calls=tool_calls)
    except AIServiceError as e:
        # Configuration/upstream problems are the operator's fault, not the user's.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
