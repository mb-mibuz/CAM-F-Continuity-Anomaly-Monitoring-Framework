# Configuration for latexmk to use pdfLaTeX
$pdf_mode = 1;  # Use pdfLaTeX
$pdflatex = 'pdflatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';
$bibtex_use = 2;  # Use biber for bibliography
$biber = 'biber %O %S';