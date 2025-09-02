# structured_parser.py
"""
Compatibilidad mínima: antes parseaba TODO con LLM de una.
Ahora exponde un helper que simplemente delega al flujo modular.
Si tu código llamaba `llm_update_state`, podés eliminarlo y usar /webhook.
"""
from typing import Dict, Any
from models.schemas import ConversationState
from steps import fill_from_text_modular, llm_parse_modular, merge_state

def llm_update_state(state: ConversationState, text: str) -> Dict[str, Any]:
    # Mantener firma similar; devuelve patch aplicado
    module_idx = state.module_idx
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    patch_llm = {}
    if patch_local:
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})
    if patch_local is None or not patch_local:
        # solo LLM si no salió nada local y el módulo lo usa
        patch_llm = llm_parse_modular(text or "", module_idx)
        if patch_llm:
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})
    return {"applied_patch": (patch_local or {}) | (patch_llm or {})}
