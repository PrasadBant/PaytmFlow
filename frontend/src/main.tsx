import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

const rootElement = document.getElementById('root');

if (rootElement) {
  const root = ReactDOM.createRoot(rootElement);

  // Render immediately; App's BootGate handles session boot + retry so a
  // slow/cold backend never shows a blank screen.
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
