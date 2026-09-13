import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { bootApp } from './app/boot';
import './index.css';

const rootElement = document.getElementById('root');

if (rootElement) {
  const root = ReactDOM.createRoot(rootElement);

  // Execute boot sequence (session initialization & MSW setup) before rendering
  bootApp().finally(() => {
    root.render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );
  });
}
