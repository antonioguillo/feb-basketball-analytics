import React from 'react';

const Error = ({ message }) => {
  return (
    <div style={{ 
      background: '#238636', 
      color: 'white', 
      padding: '10px', 
      borderRadius: '4px', 
      margin: '10px 0' 
    }}>
      Error: {message}
    </div>
  );
};

export default Error;
