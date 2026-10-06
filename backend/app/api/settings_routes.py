"""Room options and the database path. There is no cash settlement."""

from fastapi import APIRouter

from app.config.settings import get_settings

router = APIRouter()


@router.get("/settings")
def settings_index() -> dict:
    configured = get_settings()
    return {
        "database_path": configured.database_url,
        "gto_modes": ["competitive", "study"],
        "bot_kinds": ["rule", "equity", "strategy"],
        "variants": ["nlhe", "short_deck"],
        "rules": [
            "ante",
            "straddle",
            "buy_in",
            "auto_top_up",
            "time_bank",
            "seven_deuce",
            "run_it_twice",
            "rake",
            "bomb_pot",
            "insurance",
        ],
        "straddle_styles": ["utg", "mississippi", "custom"],
        "cash_settlement": False,
    }
