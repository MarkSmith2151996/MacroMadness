from fastapi import FastAPI

WIDGETS = {
    "portfolio_overview": {
        "name": "Portfolio Overview",
        "description": "All open positions with live P&L, stop distances, and targets",
        "endpoint": "portfolio",
        "data": {
            "table": {
                "enableCharts": True,
                "showAll": True,
                "columnsDefs": [
                    {"field": "ticker", "headerName": "Ticker", "cellDataType": "text", "pinned": "left", "width": 80},
                    {"field": "shares", "headerName": "Shares", "cellDataType": "number"},
                    {"field": "cost_basis", "headerName": "Basis", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "current_price", "headerName": "Price", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "unrealized_pnl", "headerName": "P&L", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "stop_loss", "headerName": "Stop", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "sector", "headerName": "Sector", "cellDataType": "text"},
                    {"field": "account", "headerName": "Account", "cellDataType": "text"},
                ],
            }
        },
        "params": [
            {"paramName": "account_type", "value": "", "label": "Account", "show": True, "type": "text"},
        ],
    },
    "catalyst_calendar": {
        "name": "Catalyst Calendar",
        "description": "Upcoming catalysts for all positions and macro events",
        "endpoint": "calendar",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "event_date", "headerName": "Date", "cellDataType": "text", "width": 100},
                    {"field": "event_type", "headerName": "Type", "cellDataType": "text", "width": 80},
                    {"field": "description", "headerName": "Event", "cellDataType": "text"},
                    {"field": "ticker", "headerName": "Ticker", "cellDataType": "text", "width": 80},
                    {"field": "impact_level", "headerName": "Impact", "cellDataType": "text", "width": 80},
                ],
            }
        },
    },
    "alert_feed": {
        "name": "Alerts",
        "description": "Recent notifications and warnings",
        "endpoint": "alerts",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "sent_at", "headerName": "Time", "cellDataType": "text", "width": 120},
                    {"field": "type", "headerName": "Type", "cellDataType": "text", "width": 100},
                    {"field": "message", "headerName": "Message", "cellDataType": "text"},
                    {"field": "priority", "headerName": "Priority", "cellDataType": "number", "width": 80},
                ],
            }
        },
    },
    "trade_scores": {
        "name": "Trade Scores",
        "description": "Closed trades with 5-dimension scoring and process vs outcome",
        "endpoint": "scores",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "ticker", "headerName": "Ticker", "cellDataType": "text", "width": 80},
                    {"field": "outcome", "headerName": "Outcome", "cellDataType": "text", "width": 80},
                    {"field": "composite_score", "headerName": "Score", "cellDataType": "number", "width": 80},
                    {"field": "research", "headerName": "Research", "cellDataType": "number", "width": 80},
                    {"field": "entry", "headerName": "Entry", "cellDataType": "number", "width": 80},
                    {"field": "sizing", "headerName": "Sizing", "cellDataType": "number", "width": 80},
                    {"field": "stop", "headerName": "Stop", "cellDataType": "number", "width": 80},
                    {"field": "exit", "headerName": "Exit", "cellDataType": "number", "width": 80},
                    {"field": "process_vs_outcome", "headerName": "Process", "cellDataType": "text"},
                ],
            }
        },
    },
    "system_health": {
        "name": "System Health",
        "description": "Schwab token, API budgets, backups, pending operations",
        "endpoint": "system-health",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "component", "headerName": "Component", "cellDataType": "text"},
                    {"field": "status", "headerName": "Status", "cellDataType": "text"},
                    {"field": "detail", "headerName": "Detail", "cellDataType": "text"},
                ],
            }
        },
    },
}


def register_all_widgets(app: FastAPI):
    from src.widgets.alerts_widget import router as alerts_router
    from src.widgets.calendar_widget import router as calendar_router
    from src.widgets.health_widget import router as health_router
    from src.widgets.portfolio_widget import router as portfolio_router
    from src.widgets.scores_widget import router as scores_router

    app.include_router(portfolio_router)
    app.include_router(calendar_router)
    app.include_router(alerts_router)
    app.include_router(scores_router)
    app.include_router(health_router)

    @app.get("/widgets.json")
    async def get_widgets():
        return WIDGETS
