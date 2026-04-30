import re
from typing import List, Dict, Any, Optional, Tuple, Callable
from . import PatchResult, build_regex_from_pieces

def detect_unicode_escaping(content: str) -> bool:
    return bool(re.search(r'\\u[0-9a-fA-F]{4}', content))

def extract_build_time(content: str) -> Optional[str]:
    match = re.search(r'\bBUILD_TIME:"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"', content)
    return match.group(1) if match else None

def escape_unescaped_char(s: str, char: str) -> str:
    result = []
    for i, c in enumerate(s):
        if c == char:
            bs = 0
            j = i - 1
            while j >= 0 and s[j] == '\\':
                bs += 1
                j -= 1
            if bs % 2 == 0:
                result.append('\\' + char)
            else:
                result.append(char)
        else:
            result.append(c)
    return "".join(result)

def apply_system_prompts(
    content: str,
    version: str,
    prompts_data: List[Dict[str, Any]],
    patch_filter: Optional[List[str]] = None
) -> Tuple[str, List[PatchResult]]:
    should_escape_non_ascii = detect_unicode_escaping(content)
    build_time = extract_build_time(content)

    results = []
    
    # Pre-process prompts to apply CCVERSION and BUILD_TIME to pieces if needed
    # (The prompts from JSON might already have these as placeholders)
    
    for prompt_entry in prompts_data:
        prompt_id = prompt_entry.get('id')
        prompt_name = prompt_entry.get('name', 'Unknown')
        
        if patch_filter and prompt_id not in patch_filter:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, skipped=True))
            continue

        pieces = prompt_entry.get('pieces', [])
        # Apply placeholders to pieces if they aren't already replaced
        processed_pieces = []
        for piece in pieces:
            p = piece.replace('<<CCVERSION>>', version)
            if build_time:
                p = p.replace('<<BUILD_TIME>>', build_time)
            processed_pieces.append(p)

        regex_pattern = build_regex_from_pieces(processed_pieces)
        
        # 's' flag in JS dotAll is 're.DOTALL' in Python
        # 'i' flag is 're.IGNORECASE'
        try:
            pattern = re.compile(regex_pattern, re.DOTALL | re.IGNORECASE)
            match = pattern.search(content)
        except Exception as e:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, failed=True, details=f"Regex error: {str(e)}"))
            continue

        if match:
            # Reconstruct content from the prompt's desired content
            # Tweakcc allows users to edit markdown files, but for now we just use the original content
            # or a simple replacement.
            # In tweakcc, prompt.content is the CUSTOM content from the user's markdown file.
            
            # For this port, let's assume we want to replace with some custom content 
            # if provided in prompt_entry, otherwise just "apply" (keep as is but mark as matched)
            
            custom_content = prompt_entry.get('custom_content')
            if not custom_content:
                # If no custom content, we don't actually change anything, just mark as found
                results.append(PatchResult(prompt_id, prompt_name, "System Prompts", True, details="Found but no custom content provided"))
                continue

            # Interpolate variables from match
            # match.groups() contains what was between the pieces
            groups = match.groups()
            
            # Tweakcc has getInterpolatedContent which puts these back into the custom content
            # We'll need a way to represent placeholders in custom_content, e.g. ${VAR}
            # For now, let's just do a simple replacement
            
            replacement = custom_content
            # TODO: Implement proper interpolation if needed
            
            # Handle delimiter escaping
            match_index = match.start()
            delimiter = content[match_index - 1] if match_index > 0 else ''
            
            if delimiter in ('"', "'"):
                replacement = replacement.replace('\n', '\\n')
                replacement = escape_unescaped_char(replacement, delimiter)
            elif delimiter == '`':
                # Backtick escaping is more complex (nested ${})
                replacement = replacement.replace('`', '\\`')
            
            # Replace in content
            # Use a lambda to avoid backreference issues
            content = content[:match.start()] + replacement + content[match.end():]
            
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", True))
        else:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, details="Prompt not found in binary"))

    return content, results
