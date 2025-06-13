# CAMF/services/export/pdf_generator.py
"""
PDF Report Generator using ReportLab for professional formatting.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
    Table, TableStyle, Flowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus.flowables import Flowable

from PIL import Image as PILImage
import numpy as np
import cv2
import os
import tempfile
from typing import List, Dict, Any


class NumberedCanvasWithBookmarks(canvas.Canvas):
    """Canvas that adds page numbers and handles bookmarks."""
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
        self._bookmarks = {}
        
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
        
    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)
        
    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 9)
        self.drawRightString(
            letter[0] - 0.75*inch,
            0.75*inch,
            f"Page {self._pageNumber} of {page_count}"
        )
    
    def bookmarkPage(self, name):
        """Override to track bookmarks."""
        self._bookmarks[name] = self._pageNumber
        super().bookmarkPage(name)


class BookmarkFlowable(Flowable):
    """Flowable that creates a bookmark anchor."""
    def __init__(self, name, fit="Fit"):
        Flowable.__init__(self)
        self.name = name
        self.fit = fit
        
    def wrap(self, availWidth, availHeight):
        return (0, 0)
        
    def draw(self):
        self.canv.bookmarkPage(self.name)
        

class TOCEntry(Flowable):
    """Custom TOC entry with dot leaders."""
    def __init__(self, level, text, pageNum, bookmarkName=None):
        Flowable.__init__(self)
        self.level = level
        self.text = text
        self.pageNum = pageNum
        self.bookmarkName = bookmarkName
        
        # Style settings based on level
        if level == 0:  # Scene
            self.fontSize = 12
            self.leftIndent = 0
            self.bold = True
        elif level == 1:  # Angle  
            self.fontSize = 11
            self.leftIndent = 20
            self.bold = True
        else:  # Take
            self.fontSize = 11
            self.leftIndent = 40
            self.bold = False
    
    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = self.fontSize + 6
        return (self.width, self.height)
    
    def draw(self):
        c = self.canv
        
        # Calculate positions
        textWidth = availWidth = self.width - self.leftIndent
        
        # Set font
        if self.bold:
            c.setFont("Helvetica-Bold", self.fontSize)
        else:
            c.setFont("Helvetica", self.fontSize)
        
        # Draw text
        x = self.leftIndent
        y = 2
        
        if self.bookmarkName and self.pageNum:
            # Make it a link
            c.saveState()
            c.setFillColor(colors.black)
            
            # Draw the text
            c.drawString(x, y, self.text)
            
            # Calculate text width
            textW = c.stringWidth(self.text, c._fontname, self.fontSize)
            
            # Draw dots if this is a take (has page number)
            if self.pageNum and self.level > 1:
                dotsStart = x + textW + 4
                pageNumWidth = c.stringWidth(str(self.pageNum), c._fontname, self.fontSize)
                dotsEnd = self.width - pageNumWidth - 4
                
                # Draw dots
                c.setFont("Helvetica", self.fontSize)
                dotWidth = c.stringWidth(".", "Helvetica", self.fontSize)
                currentX = dotsStart
                while currentX < dotsEnd:
                    c.drawString(currentX, y, ".")
                    currentX += dotWidth * 1.5
                
                # Draw page number
                c.drawRightString(self.width, y, str(self.pageNum))
            
            # Create invisible link over the whole line
            linkRect = (x, y - 2, self.width, y + self.fontSize)
            c.linkURL(f"#{self.bookmarkName}", linkRect, relative=1)
            
            c.restoreState()
        else:
            # Just draw text (for section headers without page numbers)
            c.drawString(x, y, self.text)


class PDFReportGenerator:
    """Generates professional PDF reports for continuity monitoring."""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        self.temp_dir = tempfile.mkdtemp()
        self.frame_processor = None  # Will be set from export service
        
    def _setup_custom_styles(self):
        """Setup custom paragraph styles."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        # Subtitle style with better line spacing
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Normal'],
            fontSize=16,
            textColor=HexColor('#444444'),
            spaceAfter=12,
            alignment=TA_CENTER,
            leading=22  # Increased line spacing
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=24
        ))
        
        # Notes style
        self.styles.add(ParagraphStyle(
            name='Notes',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=16,
            alignment=TA_LEFT
        ))
        
        # Frame reference style (italicized and grey)
        self.styles.add(ParagraphStyle(
            name='FrameReference',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Oblique',
            textColor=HexColor('#999999')  # Grey color
        ))
        
        # Caption style with more spacing
        self.styles.add(ParagraphStyle(
            name='Caption',
            parent=self.styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=HexColor('#666666'),
            spaceBefore=6  # Add space above caption
        ))
    
    def generate_take_report(self, report_data: Dict[str, Any], 
                           notes_section: Dict[str, Any],
                           error_frames: List[Dict[str, Any]], 
                           output_path: str):
        """Generate a single take report."""
        print(f"[PDFGenerator] Starting PDF generation for take report")
        
        # Set frame processor for color consistency
        if hasattr(self, 'frame_processor') and self.frame_processor:
            # Build color map from all errors
            all_errors = []
            for frame_data in error_frames:
                all_errors.extend(frame_data['errors'])
            self.error_color_map = self.frame_processor.get_error_color_map(all_errors)
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=1*inch
        )
        
        story = []
        
        # Cover page
        print(f"[PDFGenerator] Creating cover page...")
        story.extend(self._create_cover_page(report_data))
        story.append(PageBreak())
        
        # Notes section (no TOC for take reports)
        print(f"[PDFGenerator] Processing notes section...")
        story.append(Paragraph("Notes", self.styles['SectionHeader']))
        story.extend(self._process_notes_section(notes_section))
        
        if error_frames:
            print(f"[PDFGenerator] Processing {len(error_frames)} error frames...")
            story.append(PageBreak())
            story.append(Paragraph("Error Frames", self.styles['SectionHeader']))
            story.extend(self._create_error_frames_section(error_frames))
        
        # Build PDF
        print(f"[PDFGenerator] Building PDF document...")
        doc.build(story, canvasmaker=NumberedCanvasWithBookmarks)
        print(f"[PDFGenerator] PDF generation complete!")
    
    def generate_scene_report(self, report_data: Dict[str, Any],
                            takes_by_angle: List[Dict[str, Any]],
                            output_path: str):
        """Generate a complete scene report."""
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=1*inch
        )
        
        story = []
        
        # Cover page
        story.extend(self._create_cover_page(report_data))
        story.append(PageBreak())
        
        # Table of contents
        story.append(Paragraph("Table of Contents", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.3*inch))
        
        # Create TOC entries
        page = 3
        for angle_idx, angle_data in enumerate(takes_by_angle):
            # Angle header
            story.append(TOCEntry(
                level=1,
                text=angle_data['angle_name'],
                pageNum=None,
                bookmarkName=f"angle_{angle_idx}"
            ))
            story.append(Spacer(1, 0.05*inch))
            
            for take_idx, take_data in enumerate(angle_data['takes']):
                ref_text = " (Reference)" if take_data['is_reference'] else ""
                take_text = f"Take: {take_data['take_name']}{ref_text}"
                
                story.append(TOCEntry(
                    level=2,
                    text=take_text,
                    pageNum=page,
                    bookmarkName=f"take_{angle_idx}_{take_idx}"
                ))
                story.append(Spacer(1, 0.05*inch))
                page += 2  # Estimate
            
            story.append(Spacer(1, 0.1*inch))
        
        story.append(PageBreak())
        
        # Process each angle and its takes
        for angle_idx, angle_data in enumerate(takes_by_angle):
            # Add bookmark
            story.append(BookmarkFlowable(f"angle_{angle_idx}"))
            
            story.append(Paragraph(f"Angle: {angle_data['angle_name']}", 
                                 self.styles['SectionHeader']))
            
            for take_idx, take_data in enumerate(angle_data['takes']):
                # Add bookmark
                story.append(BookmarkFlowable(f"take_{angle_idx}_{take_idx}"))
                
                # Take header
                ref_text = " (Reference)" if take_data['is_reference'] else ""
                story.append(Paragraph(f"Take: {take_data['take_name']}{ref_text}", 
                                     self.styles['Heading2']))
                
                # Notes section
                story.append(Paragraph("Notes", self.styles['Heading3']))
                story.extend(self._process_notes_section(take_data['notes_section']))
                
                # Error frames
                if take_data['error_frames']:
                    story.append(Spacer(1, 0.5*inch))
                    story.append(Paragraph("Error Frames", self.styles['Heading3']))
                    story.extend(self._create_error_frames_section(take_data['error_frames']))
                
                # Add page break after each take (except the last)
                if not (angle_idx == len(takes_by_angle) - 1 and 
                        take_idx == len(angle_data['takes']) - 1):
                    story.append(PageBreak())
        
        # Build PDF
        doc.build(story, canvasmaker=NumberedCanvasWithBookmarks)

    def generate_project_report(self, report_data: Dict[str, Any],
                              scenes_data: List[Dict[str, Any]],
                              output_path: str):
        """Generate complete project report."""
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=1*inch
        )
        
        story = []
        
        # Cover page
        story.extend(self._create_cover_page(report_data))
        story.append(PageBreak())
        
        # Table of contents
        story.append(Paragraph("Table of Contents", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.3*inch))
        
        # Create TOC entries
        page = 3
        for scene_idx, scene_data in enumerate(scenes_data):
            # Scene header
            story.append(TOCEntry(
                level=0,
                text=scene_data['scene_name'],
                pageNum=None,
                bookmarkName=f"scene_{scene_idx}"
            ))
            story.append(Spacer(1, 0.05*inch))
            
            for angle_idx, angle_data in enumerate(scene_data['angles']):
                # Angle header
                story.append(TOCEntry(
                    level=1,
                    text=angle_data['angle_name'],
                    pageNum=None,
                    bookmarkName=f"angle_{scene_idx}_{angle_idx}"
                ))
                story.append(Spacer(1, 0.05*inch))
                
                for take_idx, take_data in enumerate(angle_data['takes']):
                    ref_text = " (Reference)" if take_data['is_reference'] else ""
                    take_text = f"Take: {take_data['take_name']}{ref_text}"
                    
                    story.append(TOCEntry(
                        level=2,
                        text=take_text,
                        pageNum=page,
                        bookmarkName=f"take_{scene_idx}_{angle_idx}_{take_idx}"
                    ))
                    story.append(Spacer(1, 0.05*inch))
                    page += 1
                
                story.append(Spacer(1, 0.05*inch))
            
            story.append(Spacer(1, 0.15*inch))
        
        story.append(PageBreak())
        
        # Process each scene
        for scene_idx, scene_data in enumerate(scenes_data):
            # Add bookmark
            story.append(BookmarkFlowable(f"scene_{scene_idx}"))
            
            story.append(Paragraph(f"Scene: {scene_data['scene_name']}", 
                                 self.styles['SectionHeader']))
            
            for angle_idx, angle_data in enumerate(scene_data['angles']):
                # Add bookmark
                story.append(BookmarkFlowable(f"angle_{scene_idx}_{angle_idx}"))
                
                story.append(Paragraph(f"Angle: {angle_data['angle_name']}", 
                                     self.styles['Heading2']))
                
                for take_idx, take_data in enumerate(angle_data['takes']):
                    # Add bookmark
                    story.append(BookmarkFlowable(f"take_{scene_idx}_{angle_idx}_{take_idx}"))
                    
                    # Take header
                    ref_text = " (Reference)" if take_data['is_reference'] else ""
                    story.append(Paragraph(f"Take: {take_data['take_name']}{ref_text}", 
                                         self.styles['Heading3']))
                    
                    # Notes section
                    story.append(Paragraph("Notes", self.styles['Heading4']))
                    story.extend(self._process_notes_section(take_data['notes_section']))
                    
                    # Error frames
                    if take_data['error_frames']:
                        story.append(Spacer(1, 0.3*inch))
                        story.append(Paragraph("Error Frames", self.styles['Heading4']))
                        story.extend(self._create_error_frames_section(take_data['error_frames']))
                    
                    # Add page break after each take (except the very last one)
                    if not (scene_idx == len(scenes_data) - 1 and 
                            angle_idx == len(scene_data['angles']) - 1 and 
                            take_idx == len(angle_data['takes']) - 1):
                        story.append(PageBreak())
        
        # Build PDF
        doc.build(story, canvasmaker=NumberedCanvasWithBookmarks)
    
    def _create_cover_page(self, report_data: Dict[str, Any]) -> List[Flowable]:
        """Create cover page elements."""
        elements = []
        
        # Spacer from top
        elements.append(Spacer(1, 2*inch))
        
        # Title based on report type
        if report_data['type'] == 'take':
            title = f"Take Report"
            subtitle = f"{report_data['project_name']} - {report_data['scene_name']}<br/>" \
                      f"{report_data['angle_name']} - {report_data['take_name']}"
        elif report_data['type'] == 'scene':
            title = f"Scene Report"
            subtitle = f"{report_data['project_name']} - {report_data['scene_name']}"
        else:  # project
            title = f"Project Report"
            subtitle = f"{report_data['project_name']}"
        
        elements.append(Paragraph(title, self.styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        elements.append(Paragraph(subtitle, self.styles['Subtitle']))
        
        # Date
        elements.append(Spacer(1, 2*inch))
        from datetime import datetime
        date_str = datetime.now().strftime("%B %d, %Y")
        elements.append(Paragraph(f"Generated: {date_str}", self.styles['Normal']))
        
        return elements
    
    def _process_notes_section(self, notes_section: Dict[str, Any]) -> List[Flowable]:
        """Process notes section with frames grouped after paragraphs."""
        elements = []
        
        # Group segments by paragraph
        current_paragraph = []
        frame_refs_in_paragraph = []
        
        for segment in notes_section['segments']:
            if segment['type'] == 'text':
                # Add text to current paragraph
                current_paragraph.append(segment['content'])
            else:
                # Frame reference - add grey reference text
                grey_ref = f'<font color="#999999"><i>{segment["original"]}</i></font>'
                current_paragraph.append(grey_ref)
                if 'frame_data' in segment:
                    frame_refs_in_paragraph.append(segment['frame_data'])
        
        # Create the paragraph with all text and references
        if current_paragraph:
            para_text = ''.join(current_paragraph)
            elements.append(Paragraph(para_text, self.styles['Notes']))
            
            # Add all referenced frames after the paragraph
            if frame_refs_in_paragraph:
                elements.append(Spacer(1, 0.3*inch))
                for frame_data in frame_refs_in_paragraph:
                    elements.extend(self._create_embedded_frame(frame_data))
                    elements.append(Spacer(1, 0.3*inch))
        
        return elements
    
    def _create_embedded_frame(self, frame_data: Dict[str, Any]) -> List[Flowable]:
        """Create embedded frame with caption."""
        elements = []
        
        print(f"[PDFGenerator] Creating embedded frame for frame {frame_data.get('frame_id', 'unknown')}")
        
        # Save frame as temporary image
        temp_path = self._save_frame_as_image(frame_data['frame'])
        print(f"[PDFGenerator] Frame saved to: {temp_path}")
        
        # Create image with proper sizing (full page width with margins)
        img = Image(temp_path, width=6.5*inch, height=4.875*inch, kind='proportional')
        elements.append(img)
        
        # Add space before caption
        elements.append(Spacer(1, 0.1*inch))
        
        # Caption
        caption = f"Frame #{frame_data['frame_id']} - Timecode: {frame_data['timecode']}"
        elements.append(Paragraph(caption, self.styles['Caption']))
        
        return elements
    
    def _create_error_frames_section(self, error_frames: List[Dict[str, Any]]) -> List[Flowable]:
        """Create error frames section with 4 frames per row."""
        elements = []
        
        # Process frames in groups of 4
        for i in range(0, len(error_frames), 4):
            frame_group = error_frames[i:i+4]
            elements.extend(self._create_frame_row(frame_group))
            elements.append(Spacer(1, 0.3*inch))
        
        return elements
    
    def _create_frame_row(self, frame_group: List[Dict[str, Any]]) -> List[Flowable]:
        """Create a row of up to 4 frames with error details."""
        elements = []
        
        # Calculate individual frame width (4 frames with spacing)
        frame_width = 1.5*inch
        frame_height = 1.125*inch
        
        # Create row data
        row_images = []
        row_captions = []
        row_errors = []
        
        for frame_data in frame_group:
            # Save frame
            temp_path = self._save_frame_as_image(frame_data['frame'])
            img = Image(temp_path, width=frame_width, height=frame_height)
            row_images.append(img)
            
            # Caption
            caption = f"{frame_data['timecode']}<br/>(Frame #{frame_data['frame_id']})"
            row_captions.append(caption)
            
            # Error list with colors matching bounding boxes
            error_list = []
            error_metadata = frame_data.get('error_metadata', [])
            
            for i, error in enumerate(frame_data['errors']):
                # Get color that matches the bounding box
                color_hex = self._get_error_color_hex(error.detector_name)
                
                # Add persistence count if available
                error_desc = error.description
                if i < len(error_metadata) and error_metadata[i].get('group_count', 1) > 1:
                    count = error_metadata[i]['group_count']
                    error_desc += f' (persisted for {count} frames)'
                
                error_text = f'<font color="{color_hex}">• {error_desc}</font>'
                error_list.append(error_text)
            row_errors.append(error_list)
        
        # Pad with empty cells if less than 4 frames
        while len(row_images) < 4:
            row_images.append("")
            row_captions.append("")
            row_errors.append([])
        
        # Create table for this row
        table_data = []
        
        # Images row
        table_data.append(row_images)
        
        # Captions row
        caption_cells = [Paragraph(cap, self.styles['Caption']) if cap else "" 
                        for cap in row_captions]
        table_data.append(caption_cells)
        
        # Errors row
        error_cells = []
        for errors in row_errors:
            if errors:
                error_para = Paragraph("<br/>".join(errors), self.styles['Caption'])
                error_cells.append(error_para)
            else:
                error_cells.append("")
        table_data.append(error_cells)
        
        # Create table with proper spacing
        col_widths = [frame_width + 0.1*inch] * 4
        table = Table(table_data, colWidths=col_widths)
        
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        elements.append(table)
        
        return elements
    
    def _save_frame_as_image(self, frame: np.ndarray) -> str:
        """Save frame as temporary image file."""
        # Convert from BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Resize if too large (max width 800px for PDF)
        height, width = frame_rgb.shape[:2]
        max_width = 800
        if width > max_width:
            scale = max_width / width
            new_width = int(width * scale)
            new_height = int(height * scale)
            frame_rgb = cv2.resize(frame_rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # Save as temporary file with lower quality for smaller file size
        temp_path = os.path.join(self.temp_dir, f"frame_{id(frame)}.jpg")
        pil_image = PILImage.fromarray(frame_rgb)
        pil_image.save(temp_path, 'JPEG', quality=70, optimize=True)
        
        return temp_path
    
    def _get_error_color_hex(self, detector_name: str) -> str:
        """Get hex color for error text (matching bounding box colors)."""
        if hasattr(self, 'error_color_map') and detector_name in self.error_color_map:
            # Convert BGR to RGB and then to hex
            bgr = self.error_color_map[detector_name]
            rgb = (bgr[2], bgr[1], bgr[0])  # BGR to RGB
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        else:
            # Enhanced color palette with better distribution
            colors = [
                '#e74c3c',  # Red
                '#3498db',  # Blue
                '#2ecc71',  # Green
                '#f39c12',  # Orange
                '#9b59b6',  # Purple
                '#1abc9c',  # Turquoise
                '#34495e',  # Dark Gray
                '#e67e22',  # Carrot
                '#95a5a6',  # Light Gray
                '#d35400',  # Pumpkin
                '#c0392b',  # Dark Red
                '#2980b9',  # Dark Blue
                '#27ae60',  # Dark Green
                '#f1c40f',  # Yellow
                '#8e44ad',  # Dark Purple
                '#16a085',  # Dark Turquoise
                '#2c3e50',  # Midnight Blue
                '#d68910',  # Dark Orange
                '#7f8c8d',  # Asbestos
                '#a93226'   # Dark Pomegranate
            ]
            
            # Use deterministic color selection based on detector name hash
            index = hash(detector_name) % len(colors)
            return colors[index]
    
    def cleanup(self):
        """Clean up temporary files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)