"""Compatibilité : stockage de calibration partagé avec Zanalyze Engine.

ENGINE_CALIBRATION_FILE désigne un fichier publié par Engine. Les anciennes
courbes apprises par Django ne sont pas automatiquement réutilisées.
"""
from engine.calibration_store import *  # noqa: F401,F403
