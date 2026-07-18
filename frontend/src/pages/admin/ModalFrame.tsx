import React from "react";
import { AnimatePresence, motion } from "framer-motion";

interface ModalFrameProps {
  ariaBusy?: boolean;
  ariaLabelledBy?: string;
  children: React.ReactNode;
  contentClassName?: string;
  isOpen: boolean;
  onClose?: () => void;
  overlayClassName?: string;
}

const ModalFrame: React.FC<ModalFrameProps> = ({
  ariaBusy,
  ariaLabelledBy,
  children,
  contentClassName,
  isOpen,
  onClose,
  overlayClassName,
}) => (
  <AnimatePresence>
    {isOpen && (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className={[
          "fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm",
          overlayClassName,
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          className={[
            "w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6",
            contentClassName,
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={(event) => event.stopPropagation()}
          role={ariaLabelledBy ? "dialog" : undefined}
          aria-modal={ariaLabelledBy ? "true" : undefined}
          aria-labelledby={ariaLabelledBy}
          aria-busy={ariaBusy}
        >
          {children}
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
);

export default ModalFrame;
