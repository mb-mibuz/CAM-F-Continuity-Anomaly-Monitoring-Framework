# CAMF/services/export/note_parser.py
"""
Note parser for extracting frame references from notes.
"""

import re
from typing import List, Dict, Any


class NoteParser:
    """Parses notes text to extract frame references."""
    
    # Pattern to match "frame #123" or "frame#123" (case insensitive)
    FRAME_REFERENCE_PATTERN = re.compile(r'frame\s*#(\d+)', re.IGNORECASE)
    
    def parse_frame_references(self, notes_text: str) -> List[Dict[str, Any]]:
        """
        Parse notes text and extract frame references.
        
        Returns list of segments, each being either:
        - {'type': 'text', 'content': '...'}
        - {'type': 'frame', 'frame_id': 123, 'original': 'frame #123'}
        """
        if not notes_text:
            return []
        
        segments = []
        last_end = 0
        
        # Find all frame references
        for match in self.FRAME_REFERENCE_PATTERN.finditer(notes_text):
            # Add text before this match
            if match.start() > last_end:
                segments.append({
                    'type': 'text',
                    'content': notes_text[last_end:match.start()]
                })
            
            # Add frame reference
            frame_id = int(match.group(1))
            segments.append({
                'type': 'frame',
                'frame_id': frame_id,
                'original': match.group(0)
            })
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(notes_text):
            segments.append({
                'type': 'text',
                'content': notes_text[last_end:]
            })
        
        return segments