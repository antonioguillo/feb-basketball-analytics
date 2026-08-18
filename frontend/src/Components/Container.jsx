import React from 'react';

const Container = ({ children }) => {
  const maxWidth = 1200;
  const padding = 24;
  
  return (
    <div style={{
      maxWidth: maxWidth,
      margin: '0 auto',
      padding: padding
    }}>
      {children}
    </div>
  );
};

export default Container;
