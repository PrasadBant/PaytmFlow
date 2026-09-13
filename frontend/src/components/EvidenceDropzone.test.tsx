import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { EvidenceDropzone } from './EvidenceDropzone';

describe('EvidenceDropzone (F18)', () => {
  it('renders dropzone with instructions and 10MB cap label', () => {
    render(<EvidenceDropzone onFileSelect={vi.fn()} />);

    expect(screen.getByText(/Click to upload/i)).toBeInTheDocument();
    expect(screen.getByText(/Supported formats: PDF, JPEG, PNG \(Max 10MB\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument();
  });

  it('accepts a valid PDF file under 10MB', () => {
    const handleSelect = vi.fn();
    render(<EvidenceDropzone onFileSelect={handleSelect} />);

    const validPdf = new File(['dummy content'], 'salary_slip.pdf', {
      type: 'application/pdf',
    });

    const fileInput = screen.getByTestId('evidence-file-input');
    fireEvent.change(fileInput, { target: { files: [validPdf] } });

    expect(handleSelect).toHaveBeenCalledWith(validPdf);
  });

  it('rejects a 12MB file exceeding 10MB limit with error message', () => {
    const handleSelect = vi.fn();
    render(<EvidenceDropzone onFileSelect={handleSelect} />);

    // Create a 12 MB file mock (12 * 1024 * 1024 bytes)
    const largeFile = new File([''], 'huge_statement.pdf', {
      type: 'application/pdf',
    });
    Object.defineProperty(largeFile, 'size', { value: 12 * 1024 * 1024 });

    const fileInput = screen.getByTestId('evidence-file-input');
    fireEvent.change(fileInput, { target: { files: [largeFile] } });

    expect(handleSelect).toHaveBeenCalledWith(null);
    expect(
      screen.getByText(/File size exceeds the 10MB limit/i)
    ).toBeInTheDocument();
  });

  it('rejects an invalid file type (.zip) with error message', () => {
    const handleSelect = vi.fn();
    render(<EvidenceDropzone onFileSelect={handleSelect} />);

    const zipFile = new File(['zip content'], 'archive.zip', {
      type: 'application/zip',
    });

    const fileInput = screen.getByTestId('evidence-file-input');
    fireEvent.change(fileInput, { target: { files: [zipFile] } });

    expect(handleSelect).toHaveBeenCalledWith(null);
    expect(
      screen.getByText(/Invalid file format. Only PDF, JPEG, and PNG files are supported/i)
    ).toBeInTheDocument();
  });

  it('renders selected file preview with remove button', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();

    const selectedFile = new File(['content'], 'bank_statement.pdf', {
      type: 'application/pdf',
    });
    Object.defineProperty(selectedFile, 'size', { value: 2.5 * 1024 * 1024 });

    render(
      <EvidenceDropzone
        selectedFile={selectedFile}
        onFileSelect={handleSelect}
      />
    );

    expect(screen.getByText('bank_statement.pdf')).toBeInTheDocument();
    expect(screen.getByText('2.50 MB')).toBeInTheDocument();

    const removeBtn = screen.getByRole('button', { name: /Remove selected file/i });
    await user.click(removeBtn);

    expect(handleSelect).toHaveBeenCalledWith(null);
  });

  it('supports drag and drop of files', () => {
    const handleSelect = vi.fn();
    render(<EvidenceDropzone onFileSelect={handleSelect} />);

    const dropzone = screen.getByTestId('evidence-dropzone');
    const validImage = new File(['img data'], 'photo.png', {
      type: 'image/png',
    });

    fireEvent.dragOver(dropzone);
    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [validImage],
      },
    });

    expect(handleSelect).toHaveBeenCalledWith(validImage);
  });

  it('is keyboard accessible via Enter or Space key', () => {
    render(<EvidenceDropzone onFileSelect={vi.fn()} />);

    const dropzone = screen.getByTestId('evidence-dropzone');
    const fileInput = screen.getByTestId('evidence-file-input');
    const clickSpy = vi.spyOn(fileInput, 'click');

    fireEvent.keyDown(dropzone, { key: 'Enter' });
    expect(clickSpy).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(dropzone, { key: ' ' });
    expect(clickSpy).toHaveBeenCalledTimes(2);
  });

  it('displays uploading state and disables remove button during upload', () => {
    const selectedFile = new File(['content'], 'statement.pdf', {
      type: 'application/pdf',
    });

    render(
      <EvidenceDropzone
        selectedFile={selectedFile}
        onFileSelect={vi.fn()}
        isUploading={true}
      />
    );

    expect(screen.getByText('Uploading...')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Remove selected file/i })).not.toBeInTheDocument();
  });

  it('strictly asserts absence of prohibited claims', () => {
    const { container } = render(<EvidenceDropzone onFileSelect={vi.fn()} />);
    const html = container.innerHTML;

    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
