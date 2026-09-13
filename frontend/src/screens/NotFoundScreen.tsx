import type React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/primitives/Button';

export const NotFoundScreen: React.FC = () => {
  return (
    <div data-testid="screen-404" className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="text-6xl font-extrabold text-paytm-blue mb-4">404</div>
      <h1 className="text-2xl font-bold text-content-primary mb-2">Page Not Found</h1>
      <p className="text-content-secondary max-w-md mb-6">
        The page or journey you are looking for does not exist or has moved.
      </p>
      <Link to="/">
        <Button variant="primary">Return to Home</Button>
      </Link>
    </div>
  );
};
