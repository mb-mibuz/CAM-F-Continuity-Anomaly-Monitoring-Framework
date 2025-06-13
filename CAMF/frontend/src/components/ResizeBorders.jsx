// src/components/ResizeBorders.jsx
import React from 'react';

export default function ResizeBorders() {
  return (
    <>
      {/* Edge resize borders */}
      <div className="resize-border resize-border-top" />
      <div className="resize-border resize-border-bottom" />
      <div className="resize-border resize-border-left" />
      <div className="resize-border resize-border-right" />
      
      {/* Corner resize borders */}
      <div className="resize-border resize-border-topleft" />
      <div className="resize-border resize-border-topright" />
      <div className="resize-border resize-border-bottomleft" />
      <div className="resize-border resize-border-bottomright" />
    </>
  );
}