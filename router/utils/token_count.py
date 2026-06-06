from __future__ import annotations

# SYMBOLS defined for cl100k_base symbol recognition
SYMBOLS = "!@#$%^&*()_+-=[]{}|;:'\",.<>/?\\"
TRANS_TABLE = str.maketrans('', '', SYMBOLS)

def fast_estimate_tokens(prompt: str, alpha: float = 1.25, beta: float = 0.22, symbol_weight: float = 0.75) -> int:
    """
    Ultra-fast hybrid estimation (Math + C-level symbol counting).
    
    Optimized for cl100k_base (GPT-4) with a slightly conservative bias (+5% to +30%).
    Performance: ~7 microseconds per request.
    
    :param prompt: The text to estimate tokens for.
    :param alpha: Weight for Chinese characters.
    :param beta: Weight for English/ASCII characters.
    :param symbol_weight: Additional weight for symbols (code/punctuation).
    :return: Estimated token count.
    """
    if not prompt:
        return 0
    
    try:
        # Get character length and byte length (UTF-8)
        l_char = len(prompt)
        l_byte = len(prompt.encode('utf-8'))
        
        # Calculate Chinese characters (3-byte in UTF-8 BMP)
        # (l_byte - l_char) / 2 is a mathematical shortcut for CN count in mixed text
        c_zh = max(0.0, (l_byte - l_char) / 2.0)
        
        # Calculate English/ASCII characters
        c_en = max(0.0, l_char - c_zh)
        
        # Fast symbol counting using C-level translate
        symbol_count = l_char - len(prompt.translate(TRANS_TABLE))
        
        # Final weighted sum
        return int((c_zh * alpha) + (c_en * beta) + (symbol_count * symbol_weight))
    except Exception:
        # Fallback to a very safe character-based estimate if something goes wrong
        return len(prompt)
