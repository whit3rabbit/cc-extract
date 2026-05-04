"""Provider splash art rendered by generated variant wrappers."""

import shlex
from typing import Dict, Iterable, List, Tuple


RESET = r"\033[0m"


PALETTES: Dict[str, Tuple[str, str, str, str]] = {
    "9router": (r"\033[38;5;208m", r"\033[38;5;75m", r"\033[38;5;45m", r"\033[38;5;240m"),
    "alibaba": (r"\033[38;5;51m", r"\033[38;5;81m", r"\033[38;5;141m", r"\033[38;5;60m"),
    "anthropic": (r"\033[38;5;216m", r"\033[38;5;223m", r"\033[38;5;215m", r"\033[38;5;94m"),
    "ccrouter": (r"\033[38;5;39m", r"\033[38;5;45m", r"\033[38;5;33m", r"\033[38;5;31m"),
    "cerebras": (r"\033[38;5;214m", r"\033[38;5;220m", r"\033[38;5;208m", r"\033[38;5;94m"),
    "custom": (r"\033[38;5;255m", r"\033[38;5;183m", r"\033[38;5;147m", r"\033[38;5;245m"),
    "deepseek": (r"\033[38;5;39m", r"\033[38;5;75m", r"\033[38;5;33m", r"\033[38;5;25m"),
    "gatewayz": (r"\033[38;5;141m", r"\033[38;5;135m", r"\033[38;5;99m", r"\033[38;5;60m"),
    "kimi": (r"\033[38;5;81m", r"\033[38;5;75m", r"\033[38;5;69m", r"\033[38;5;67m"),
    "minimax": (r"\033[38;5;203m", r"\033[38;5;209m", r"\033[38;5;208m", r"\033[38;5;167m"),
    "minimax-cn": (r"\033[38;5;196m", r"\033[38;5;214m", r"\033[38;5;220m", r"\033[38;5;88m"),
    "mirror": (r"\033[38;5;252m", r"\033[38;5;250m", r"\033[38;5;45m", r"\033[38;5;243m"),
    "nanogpt": (r"\033[38;5;120m", r"\033[38;5;51m", r"\033[38;5;154m", r"\033[38;5;66m"),
    "ollama": (r"\033[38;5;180m", r"\033[38;5;223m", r"\033[38;5;137m", r"\033[38;5;101m"),
    "openrouter": (r"\033[38;5;252m", r"\033[38;5;250m", r"\033[38;5;45m", r"\033[38;5;243m"),
    "poe": (r"\033[38;5;141m", r"\033[38;5;177m", r"\033[38;5;99m", r"\033[38;5;60m"),
    "vercel": (r"\033[38;5;255m", r"\033[38;5;250m", r"\033[38;5;34m", r"\033[38;5;240m"),
    "zai": (r"\033[38;5;220m", r"\033[38;5;214m", r"\033[38;5;208m", r"\033[38;5;172m"),
    "default": (r"\033[38;5;255m", r"\033[38;5;250m", r"\033[38;5;45m", r"\033[38;5;245m"),
}


SPLASH_TEXT: Dict[str, Tuple[str, ...]] = {
    "9router": ("   9ROUTER", "  [ LOCAL AI GATEWAY ]", "  FALLBACK READY"),
    "alibaba": ("   ALIBABA CLOUD", "  [ DASH SCOPE ]", "  QWEN CODING LANE"),
    "anthropic": ("   ANTHROPIC", "  < CONSOLE API >", "  FIRST PARTY CLAUDE"),
    "ccrouter": ("   CC ROUTER", "  < ANY MODEL >", "  LOCAL ROUTE ONLINE"),
    "cerebras": ("   CEREBRAS", "  [ WAFER SCALE ]", "  ROUTED VIA CCR"),
    "custom": ("   CUSTOM", "  [ BRING YOUR ENDPOINT ]", "  CONFIGURED VARIANT"),
    "deepseek": ("   DEEPSEEK", "  < REASONING DEPTH >", "  CODE SEARCH MODE"),
    "gatewayz": ("   GATEWAYZ", "  [ MULTI MODEL GATEWAY ]", "  ROUTING ACTIVE"),
    "kimi": ("   KIMI CODE", "  < LONG CONTEXT >", "  MOONSHOT CODING"),
    "minimax": ("   MINIMAX", "  [ MODEL SPECTRUM ]", "  AGI FOR ALL"),
    "minimax-cn": ("   MINIMAX CN", "  [ MODEL SPECTRUM ]", "  CHINA API ROUTE"),
    "mirror": ("   MIRROR CLAUDE", "  < CLEAN REFLECTION >", "  ISOLATED VANILLA"),
    "nanogpt": ("   NANOGPT", "  [ ANY MODEL ]", "  PAY PER TOKEN"),
    "ollama": ("   OLLAMA", "  < LOCAL FIRST >", "  MODELS NEARBY"),
    "openrouter": ("   OPENROUTER", "  [ ONE API ]", "  ANY MODEL"),
    "poe": ("   POE", "  < MODEL HUB >", "  TOKEN ROUTE READY"),
    "vercel": ("   VERCEL", "  [ AI GATEWAY ]", "  EDGE ROUTE ACTIVE"),
    "zai": ("   ZAI CLOUD", "  < GLM CODING PLAN >", "  REASONING ONLINE"),
    "default": ("   CC EXTRACTOR", "  [ PROVIDER VARIANT ]", "  CLAUDE CODE WRAPPED"),
}


def known_styles() -> Tuple[str, ...]:
    return tuple(sorted(style for style in SPLASH_TEXT if style != "default"))


def has_style(style: str) -> bool:
    return style in SPLASH_TEXT


def splash_lines(style: str) -> Tuple[str, ...]:
    """Return ANSI-colored splash lines for a known provider style."""
    resolved = style if has_style(style) else "default"
    primary, secondary, accent, dim = PALETTES[resolved]
    text = SPLASH_TEXT[resolved]
    width = max(len(line) for line in text) + 4
    rule = "=" * width
    return (
        "",
        f"{dim}+{rule}+{RESET}",
        f"{primary}|  {text[0].ljust(width - 2)}|{RESET}",
        f"{secondary}|  {text[1].ljust(width - 2)}|{RESET}",
        f"{accent}|  {text[2].ljust(width - 2)}|{RESET}",
        f"{dim}+{rule}+{RESET}",
        "",
    )


def shell_splash_lines(styles: Iterable[str] = None) -> List[str]:
    """Return POSIX shell lines that render splash art from wrapper env."""
    styles = tuple(styles or known_styles())
    lines = [
        'if [ "${CC_EXTRACTOR_SPLASH:-0}" = "1" ] && [ -t 1 ]; then',
        "  __cc_extractor_skip_splash=0",
        '  for __cc_extractor_arg in "$@"; do',
        '    case "$__cc_extractor_arg" in',
        "      --output-format|--output-format=*|--print|-p) __cc_extractor_skip_splash=1 ;;",
        "    esac",
        "  done",
        '  if [ "$__cc_extractor_skip_splash" = "0" ]; then',
        '    __cc_extractor_style="${CC_EXTRACTOR_SPLASH_STYLE:-default}"',
        '    __cc_extractor_label="${CC_EXTRACTOR_PROVIDER_LABEL:-cc-extractor}"',
        '    __cc_extractor_known_style=1',
        '    case "$__cc_extractor_style" in',
    ]
    for style in styles:
        lines.extend(_shell_style_case(style))
    lines.extend(
        [
            "      *)",
            "        __cc_extractor_known_style=0",
            *(_shell_print_line(line) for line in splash_lines("default")),
            "        ;;",
            "    esac",
            '    if [ "$__cc_extractor_known_style" = "0" ]; then',
            '      printf " %s\\n\\n" "$__cc_extractor_label"',
            "    fi",
            "  fi",
            "fi",
        ]
    )
    return lines


def _shell_style_case(style: str) -> List[str]:
    lines = [f"      {style})"]
    lines.extend(_shell_print_line(line) for line in splash_lines(style))
    lines.append("        ;;")
    return lines


def _shell_print_line(line: str) -> str:
    return f"        printf '%b\\n' {shlex.quote(line)}"
