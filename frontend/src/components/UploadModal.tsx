import { AnimatePresence, motion } from "framer-motion";
import { FiFileText, FiUploadCloud, FiX } from "react-icons/fi";
import UploadSourcePanel from "./UploadSourcePanel";
import UploadDetailsForm from "./upload-modal/UploadDetailsForm";
import type { UploadModalProps } from "./upload-modal/types";
import { useUploadModal } from "./upload-modal/useUploadModal";

const UploadModal = (props: UploadModalProps) => {
  const { isOpen, onClose, initialData } = props;
  const controller = useUploadModal(props);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] bg-black/75 backdrop-blur-md"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 18 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 18 }}
            transition={{ duration: 0.22 }}
            className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center p-2 sm:p-5"
          >
            <div
              className={[
                "pointer-events-auto flex max-h-[96vh] w-full max-w-4xl flex-col",
                "overflow-hidden rounded-[28px] border border-white/[0.1] bg-[#0c0f0d]",
                "shadow-[0_36px_120px_rgba(0,0,0,0.65)]",
              ].join(" ")}
            >
              <header className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4 sm:px-7">
                <div className="flex items-center gap-3">
                  <div
                    className={[
                      "flex h-10 w-10 items-center justify-center rounded-2xl",
                      controller.isInvoice
                        ? "bg-[#7397ff]/10 text-[#9ab1ff]"
                        : "bg-[#b8f15a]/10 text-[#b8f15a]",
                    ].join(" ")}
                  >
                    <FiFileText />
                  </div>
                  <div>
                    <p className="eyebrow">
                      {initialData ? "Document review" : "New intake"}
                    </p>
                    <h2 className="mt-1 text-lg font-semibold">
                      {initialData
                        ? `${controller.documentLabel} bearbeiten`
                        : `${controller.documentLabel} erfassen`}
                    </h2>
                  </div>
                </div>
                <button onClick={onClose} className="icon-btn">
                  <FiX size={18} />
                </button>
              </header>

              <form onSubmit={controller.handleSubmit} className="overflow-y-auto">
                <div className="grid lg:grid-cols-[0.82fr_1.18fr]">
                  <UploadSourcePanel
                    file={controller.file}
                    fileError={controller.fileError}
                    initialData={initialData}
                    documentLabel={controller.documentLabel}
                    isDragActive={controller.dropzone.isDragActive}
                    analyzing={controller.analyzing}
                    uploading={controller.uploading}
                    getRootProps={controller.dropzone.getRootProps}
                    getInputProps={controller.dropzone.getInputProps}
                    onAnalyze={controller.handleAnalyze}
                  />
                  <UploadDetailsForm controller={controller} />
                </div>

                <footer
                  className={[
                    "flex flex-col-reverse gap-2 border-t border-white/[0.07] bg-black/15",
                    "px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7",
                  ].join(" ")}
                >
                  <p className="text-xs text-white/28">
                    Pflichtfelder werden vor dem Speichern geprüft.
                  </p>
                  <div className="flex gap-2">
                    <button type="button" onClick={onClose} className="btn-ghost">
                      Abbrechen
                    </button>
                    <button
                      type="submit"
                      disabled={
                        controller.uploading ||
                        (!initialData &&
                          (!controller.file || controller.workspaceId === 0))
                      }
                      className="btn-primary min-w-40"
                    >
                      <FiUploadCloud />{" "}
                      {controller.uploading
                        ? initialData
                          ? "Speichern …"
                          : "Hochladen …"
                        : initialData
                          ? "Änderungen speichern"
                          : `${controller.documentLabel} hochladen`}
                    </button>
                  </div>
                </footer>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export default UploadModal;
