import { useDropzone } from "react-dropzone";
import { FiRefreshCw } from "react-icons/fi";
import { ACCEPTED_UPLOAD_TYPES, describeFileRejections, MAX_UPLOAD_SIZE } from "./useUploadFiles";

interface ReplaceFileButtonProps {
  name: string;
  disabled?: boolean;
  onReplace: (file: File) => void;
  onError: (message: string) => void;
}

const ReplaceFileButton = ({ name, disabled, onReplace, onError }: ReplaceFileButtonProps) => {
  const { getInputProps, open } = useDropzone({
    accept: ACCEPTED_UPLOAD_TYPES,
    multiple: false,
    maxSize: MAX_UPLOAD_SIZE,
    minSize: 1,
    disabled,
    onDrop: (accepted, rejected) => {
      if (disabled) return;
      if (rejected.length) onError(describeFileRejections(rejected).join(" "));
      else if (accepted[0]) onReplace(accepted[0]);
    },
  });

  return (
    <>
      <input {...getInputProps({ "aria-label": `Ersatzdatei für ${name} auswählen` })} />
      <button
        type="button" onClick={open} disabled={disabled} aria-label={`${name} ersetzen`}
        className="btn-ghost shrink-0 gap-1.5 px-2 text-xs disabled:opacity-40"
      >
        <FiRefreshCw size={14} /> Ersetzen
      </button>
    </>
  );
};

export default ReplaceFileButton;
