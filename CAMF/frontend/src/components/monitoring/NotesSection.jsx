import React, { useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Bold, Italic, Underline, Strikethrough, List, Link, X } from 'lucide-react';

const NotesSection = forwardRef(({ 
  initialNotes,
  onNotesChange,
  onExport,
  onClear,
  onLinkFrame,
  frameCount = 0,
  isExportDisabled = false
}, ref) => {
  const notesRef = useRef(null);
  const undoStack = useRef([]);
  const redoStack = useRef([]);
  const isUndoRedo = useRef(false);

  // Expose methods to parent
  useImperativeHandle(ref, () => ({
    getMarkdown: () => convertHtmlToMarkdown(notesRef.current),
    setHtml: (html) => {
      if (notesRef.current) {
        notesRef.current.innerHTML = html;
      }
    },
    convertMarkdownToHtml,
    insertAtCursor: (text) => {
      if (notesRef.current) {
        notesRef.current.focus();
        document.execCommand('insertHTML', false, text);
        saveState();
        handleInput();
      }
    }
  }));

  // Convert markdown to HTML
  const convertMarkdownToHtml = (text) => {
    let html = text || '';
    
    // Convert frame links to italicized text
    html = html.replace(/\[Frame #(\d+)\]/g, 
      '<em>Frame #$1</em>');
    
    // Convert formatting
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/__(.+?)__/g, '<u>$1</u>');
    html = html.replace(/~~(.+?)~~/g, '<del>$1</del>');
    
    // Convert bullet points
    const lines = html.split('\n');
    const processedLines = [];
    let inList = false;
    
    lines.forEach(line => {
      if (line.trim().startsWith('• ')) {
        if (!inList) {
          processedLines.push('<ul>');
          inList = true;
        }
        processedLines.push(`<li>${line.trim().substring(2)}</li>`);
      } else {
        if (inList) {
          processedLines.push('</ul>');
          inList = false;
        }
        processedLines.push(line || '<br>');
      }
    });
    
    if (inList) {
      processedLines.push('</ul>');
    }
    
    return processedLines.join('');
  };

  // Convert HTML to markdown
  const convertHtmlToMarkdown = (element) => {
    let markdown = '';
    
    const processNode = (node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        markdown += node.textContent;
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = node.tagName.toLowerCase();
        
        switch (tag) {
          case 'strong':
          case 'b':
            markdown += '**';
            Array.from(node.childNodes).forEach(processNode);
            markdown += '**';
            break;
            
          case 'em':
          case 'i':
            // Check if this is a frame link
            const text = node.textContent;
            if (text && text.match(/^Frame #\d+$/)) {
              markdown += `[${text}]`;
            } else {
              markdown += '*';
              Array.from(node.childNodes).forEach(processNode);
              markdown += '*';
            }
            break;
            
          case 'u':
            markdown += '__';
            Array.from(node.childNodes).forEach(processNode);
            markdown += '__';
            break;
            
          case 'del':
          case 's':
            markdown += '~~';
            Array.from(node.childNodes).forEach(processNode);
            markdown += '~~';
            break;
            
          case 'span':
            Array.from(node.childNodes).forEach(processNode);
            break;
            
          case 'br':
            markdown += '\n';
            break;
            
          case 'li':
            markdown += '• ';
            Array.from(node.childNodes).forEach(processNode);
            markdown += '\n';
            break;
            
          case 'ul':
          case 'div':
          case 'p':
            Array.from(node.childNodes).forEach(processNode);
            if (node.nextSibling) {
              markdown += '\n';
            }
            break;
            
          default:
            Array.from(node.childNodes).forEach(processNode);
        }
      }
    };
    
    Array.from(element.childNodes).forEach(processNode);
    
    return markdown.trimEnd();
  };

  // Initialize with content
  useEffect(() => {
    if (initialNotes && notesRef.current) {
      notesRef.current.innerHTML = convertMarkdownToHtml(initialNotes);
      undoStack.current = [notesRef.current.innerHTML];
    }
  }, []);

  // Save state for undo/redo
  const saveState = () => {
    if (!isUndoRedo.current && notesRef.current) {
      const currentContent = notesRef.current.innerHTML;
      const lastState = undoStack.current[undoStack.current.length - 1];
      
      if (currentContent !== lastState) {
        undoStack.current.push(currentContent);
        if (undoStack.current.length > 50) {
          undoStack.current.shift();
        }
        redoStack.current = [];
      }
    }
  };

  // Handle input
  const handleInput = () => {
    saveState();
    
    if (notesRef.current && onNotesChange) {
      const markdown = convertHtmlToMarkdown(notesRef.current);
      onNotesChange(markdown);
    }
  };

  // Handle formatting
  const handleFormat = (format) => {
    const selection = window.getSelection();
    if (!selection.rangeCount) return;
    
    switch (format) {
      case 'bold':
        document.execCommand('bold');
        break;
      case 'italic':
        document.execCommand('italic');
        break;
      case 'underline':
        document.execCommand('underline');
        break;
      case 'strikethrough':
        document.execCommand('strikeThrough');
        break;
      case 'bullet':
        document.execCommand('insertUnorderedList');
        break;
    }
    
    notesRef.current.focus();
    saveState();
  };

  // Handle key events
  const handleKeyDown = (e) => {
    if (e.ctrlKey || e.metaKey) {
      switch (e.key) {
        case 'z':
          if (e.shiftKey) {
            e.preventDefault();
            handleRedo();
          } else {
            e.preventDefault();
            handleUndo();
          }
          break;
        case 'b':
          e.preventDefault();
          handleFormat('bold');
          break;
        case 'i':
          e.preventDefault();
          handleFormat('italic');
          break;
        case 'u':
          e.preventDefault();
          handleFormat('underline');
          break;
      }
    }
  };

  // Undo/Redo
  const handleUndo = () => {
    if (undoStack.current.length > 1) {
      isUndoRedo.current = true;
      const currentState = undoStack.current.pop();
      redoStack.current.push(currentState);
      const previousState = undoStack.current[undoStack.current.length - 1];
      notesRef.current.innerHTML = previousState;
      if (onNotesChange) {
        onNotesChange(convertHtmlToMarkdown(notesRef.current));
      }
      isUndoRedo.current = false;
    }
  };

  const handleRedo = () => {
    if (redoStack.current.length > 0) {
      isUndoRedo.current = true;
      const redoState = redoStack.current.pop();
      undoStack.current.push(redoState);
      notesRef.current.innerHTML = redoState;
      if (onNotesChange) {
        onNotesChange(convertHtmlToMarkdown(notesRef.current));
      }
      isUndoRedo.current = false;
    }
  };


  return (
    <div className="flex flex-col h-full border border-gray-300 rounded-lg overflow-hidden bg-white">
      {/* Editor area */}
      <div className="flex-1 overflow-y-auto p-4">
        <div
          ref={notesRef}
          contentEditable
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          className="notes-editor w-full h-full outline-none text-14"
          style={{ 
            minHeight: '200px',
            fontFamily: 'inherit',
            lineHeight: '1.6'
          }}
          placeholder="Add your notes here..."
        />
      </div>
      
      {/* Toolbar */}
      <div className="flex items-center justify-center gap-1 px-3 py-2 border-t border-gray-200 bg-gray-50">
        <button
          onClick={() => handleFormat('bold')}
          className="p-1.5 hover:bg-gray-200 rounded"
          title="Bold (Ctrl+B)"
        >
          <Bold size={16} />
        </button>
        
        <button
          onClick={() => handleFormat('italic')}
          className="p-1.5 hover:bg-gray-200 rounded"
          title="Italic (Ctrl+I)"
        >
          <Italic size={16} />
        </button>
        
        <button
          onClick={() => handleFormat('underline')}
          className="p-1.5 hover:bg-gray-200 rounded"
          title="Underline (Ctrl+U)"
        >
          <Underline size={16} />
        </button>
        
        <button
          onClick={() => handleFormat('strikethrough')}
          className="p-1.5 hover:bg-gray-200 rounded"
          title="Strikethrough"
        >
          <Strikethrough size={16} />
        </button>
        
        <button
          onClick={() => handleFormat('bullet')}
          className="p-1.5 hover:bg-gray-200 rounded"
          title="Bullet List"
        >
          <List size={16} />
        </button>
        
        <div className="w-px h-5 bg-gray-300 mx-2" />
        
        <button
          onClick={onLinkFrame}
          disabled={frameCount === 0}
          className={`
            flex items-center gap-1 px-2 py-1 hover:bg-gray-200 rounded text-12
            ${frameCount === 0 ? 'opacity-50 cursor-not-allowed' : ''}
          `}
          title="Link to frame"
        >
          <Link size={14} />
          Link frame
        </button>
        
        <button
          onClick={onClear}
          className="flex items-center gap-1 px-2 py-1 hover:bg-gray-200 rounded text-12"
          title="Clear all notes"
        >
          <X size={14} />
          Clear
        </button>
      </div>
      
      <style>{`
        .notes-editor:empty:before {
          content: attr(placeholder);
          color: #9CA3AF;
          font-style: italic;
          pointer-events: none;
          display: block;
        }
        
        .notes-editor ul {
          list-style-type: disc;
          margin: 0;
          padding-left: 20px;
        }
        
        .notes-editor li {
          margin: 4px 0;
        }
      `}</style>
    </div>
  );
});

NotesSection.displayName = 'NotesSection';

export default NotesSection;