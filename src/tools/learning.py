"""Module D: Learning tools (2 tools) + internal scoring."""

import math
from datetime import datetime, timezone
from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from src.db import async_session
from src.models import DimensionWeight, Lesson, Trade, TradeScore


async def score_trade(
    trade_id: int,
    research_quality_score: int,
    entry_timing_score: int,
    position_sizing_score: int,
    stop_loss_score: int,
    exit_timing_score: int,
    research_quality_notes: str = "",
    entry_timing_notes: str = "",
    position_sizing_notes: str = "",
    stop_loss_notes: str = "",
    exit_timing_notes: str = "",
) -> dict:
    """Score a closed trade on 5 dimensions (1-10 each)."""
    async with async_session() as db:
        trade = await db.get(Trade, trade_id)
        if not trade:
            return {"error": f"Trade {trade_id} not found"}

        # Get current weights
        result = await db.execute(
            select(DimensionWeight).order_by(DimensionWeight.version.desc()).limit(1)
        )
        weights = result.scalar_one_or_none()
        if not weights:
            # Default equal weights
            w = {"rq": 0.2, "et": 0.2, "ps": 0.2, "sl": 0.2, "ex": 0.2}
        else:
            w = {
                "rq": float(weights.research_quality_weight),
                "et": float(weights.entry_timing_weight),
                "ps": float(weights.position_sizing_weight),
                "sl": float(weights.stop_loss_weight),
                "ex": float(weights.exit_timing_weight),
            }

        composite = (
            research_quality_score * w["rq"]
            + entry_timing_score * w["et"]
            + position_sizing_score * w["ps"]
            + stop_loss_score * w["sl"]
            + exit_timing_score * w["ex"]
        )

        # Process vs outcome
        good_process = composite >= 7.0
        good_outcome = trade.outcome == "win"
        if good_process and good_outcome:
            pvo = "good_process_good_outcome"
        elif good_process and not good_outcome:
            pvo = "good_process_bad_outcome"
        elif not good_process and good_outcome:
            pvo = "bad_process_good_outcome"
        else:
            pvo = "bad_process_bad_outcome"

        score = TradeScore(
            trade_id=trade_id,
            research_quality_score=research_quality_score,
            entry_timing_score=entry_timing_score,
            position_sizing_score=position_sizing_score,
            stop_loss_score=stop_loss_score,
            exit_timing_score=exit_timing_score,
            research_quality_notes=research_quality_notes or None,
            entry_timing_notes=entry_timing_notes or None,
            position_sizing_notes=position_sizing_notes or None,
            stop_loss_notes=stop_loss_notes or None,
            exit_timing_notes=exit_timing_notes or None,
            composite_score=Decimal(str(round(composite, 2))),
            outcome=trade.outcome,
            process_vs_outcome=pvo,
        )
        db.add(score)
        await db.commit()
        await db.refresh(score)

    return {
        "score_id": score.id,
        "composite_score": round(composite, 2),
        "process_vs_outcome": pvo,
        "flag": "BAD PROCESS, GOOD OUTCOME — review!" if pvo == "bad_process_good_outcome" else None,
    }


def register_learning_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_weights(
        action: str,
        research_quality_weight: float = 0,
        entry_timing_weight: float = 0,
        position_sizing_weight: float = 0,
        stop_loss_weight: float = 0,
        exit_timing_weight: float = 0,
        update_reason: str = "",
    ) -> dict:
        """Manage scoring dimension weights.
        action: get | update | history
        - get: return current weights
        - update: set new weights (must sum to 1.0)
        - history: return all weight versions"""
        async with async_session() as db:
            if action == "get":
                result = await db.execute(
                    select(DimensionWeight).order_by(DimensionWeight.version.desc()).limit(1)
                )
                w = result.scalar_one_or_none()
                if not w:
                    return {"error": "No weights configured"}
                return {
                    "version": w.version,
                    "weights": {
                        "research_quality": float(w.research_quality_weight),
                        "entry_timing": float(w.entry_timing_weight),
                        "position_sizing": float(w.position_sizing_weight),
                        "stop_loss": float(w.stop_loss_weight),
                        "exit_timing": float(w.exit_timing_weight),
                    },
                    "update_method": w.update_method,
                    "effective_from": w.effective_from.isoformat(),
                }

            elif action == "history":
                result = await db.execute(
                    select(DimensionWeight).order_by(DimensionWeight.version.desc())
                )
                versions = result.scalars().all()
                return {
                    "versions": [
                        {
                            "version": v.version,
                            "weights": {
                                "research_quality": float(v.research_quality_weight),
                                "entry_timing": float(v.entry_timing_weight),
                                "position_sizing": float(v.position_sizing_weight),
                                "stop_loss": float(v.stop_loss_weight),
                                "exit_timing": float(v.exit_timing_weight),
                            },
                            "method": v.update_method,
                            "reason": v.update_reason,
                            "effective_from": v.effective_from.isoformat(),
                        }
                        for v in versions
                    ]
                }

            elif action == "update":
                total = (
                    research_quality_weight + entry_timing_weight
                    + position_sizing_weight + stop_loss_weight + exit_timing_weight
                )
                if abs(total - 1.0) > 0.001:
                    return {"error": f"Weights must sum to 1.0, got {total}"}

                # Get current version
                result = await db.execute(
                    select(DimensionWeight).order_by(DimensionWeight.version.desc()).limit(1)
                )
                current = result.scalar_one_or_none()
                new_version = (current.version + 1) if current else 1

                # Count trades for context
                trade_count_result = await db.execute(
                    select(func.count()).select_from(Trade).where(Trade.outcome.isnot(None))
                )
                trade_count = trade_count_result.scalar()

                # Determine update method
                if trade_count < 5:
                    method = "initial"
                elif trade_count < 10:
                    method = "nudge"
                else:
                    method = "recalibration"

                # Enforce floor/ceiling
                weights_list = [
                    research_quality_weight, entry_timing_weight,
                    position_sizing_weight, stop_loss_weight, exit_timing_weight,
                ]
                for w in weights_list:
                    if w < 0.10 or w > 0.35:
                        return {"error": "Each weight must be between 0.10 and 0.35"}

                new_weights = DimensionWeight(
                    version=new_version,
                    trade_count=trade_count,
                    research_quality_weight=Decimal(str(research_quality_weight)),
                    entry_timing_weight=Decimal(str(entry_timing_weight)),
                    position_sizing_weight=Decimal(str(position_sizing_weight)),
                    stop_loss_weight=Decimal(str(stop_loss_weight)),
                    exit_timing_weight=Decimal(str(exit_timing_weight)),
                    update_reason=update_reason or f"Manual update at {trade_count} trades",
                    update_method=method,
                )
                db.add(new_weights)
                await db.commit()

                return {
                    "version": new_version,
                    "method": method,
                    "trade_count": trade_count,
                    "updated": True,
                }

            return {"error": f"Unknown action: {action}. Use get, update, or history."}

    @mcp.tool()
    async def invest_lessons(
        action: str,
        lesson_text: str = "",
        lesson_type: str = "",
        sector_tag: str = "",
        catalyst_tag: str = "",
        outcome_tag: str = "",
        trade_id: int = 0,
        search_sector: str = "",
        search_catalyst: str = "",
        limit: int = 10,
    ) -> dict:
        """Manage trading lessons.
        action: search | add
        - search: find relevant lessons with relevance scoring
        - add: add a new lesson from a trade"""
        async with async_session() as db:
            if action == "add":
                if not lesson_text:
                    return {"error": "lesson_text is required"}
                lesson = Lesson(
                    trade_id=trade_id or None,
                    lesson_text=lesson_text,
                    lesson_type=lesson_type or None,
                    sector_tag=sector_tag or None,
                    catalyst_tag=catalyst_tag or None,
                    outcome_tag=outcome_tag or None,
                )
                db.add(lesson)
                await db.commit()
                await db.refresh(lesson)
                return {"lesson_id": lesson.id, "added": True}

            elif action == "search":
                result = await db.execute(select(Lesson).order_by(Lesson.created_at.desc()))
                all_lessons = result.scalars().all()

                now = datetime.now(timezone.utc)
                scored = []
                for l in all_lessons:
                    # Relevance scoring per spec
                    sector_match = 1.0 if (search_sector and l.sector_tag and search_sector.lower() == l.sector_tag.lower()) else 0.0
                    catalyst_match = 1.0 if (search_catalyst and l.catalyst_tag and search_catalyst.lower() == l.catalyst_tag.lower()) else 0.0

                    days_since = (now - l.created_at).days if l.created_at else 0
                    recency = math.exp(-0.693 * days_since / 90)

                    severity = 1.0 if l.outcome_tag == "loss" else 0.6

                    relevance = (
                        sector_match * 0.35
                        + catalyst_match * 0.30
                        + recency * 0.20
                        + severity * 0.15
                    )

                    scored.append({
                        "id": l.id,
                        "lesson_text": l.lesson_text,
                        "lesson_type": l.lesson_type,
                        "sector_tag": l.sector_tag,
                        "catalyst_tag": l.catalyst_tag,
                        "outcome_tag": l.outcome_tag,
                        "relevance": round(relevance, 3),
                        "created_at": l.created_at.isoformat(),
                    })

                scored.sort(key=lambda x: x["relevance"], reverse=True)
                return {"lessons": scored[:limit], "total": len(scored)}

            return {"error": f"Unknown action: {action}. Use search or add."}
