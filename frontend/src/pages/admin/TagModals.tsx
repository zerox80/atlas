import React from "react";
import ModalFrame from "./ModalFrame";
import type { Tag } from "./types";

interface TagFieldsProps {
  color: string;
  name: string;
  setColor: (value: string) => void;
  setName: (value: string) => void;
}

const TagFields: React.FC<TagFieldsProps> = ({
  color,
  name,
  setColor,
  setName,
}) => (
  <>
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-400">
        Name
      </label>
      <input
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        className={[
          "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
          "text-white focus:border-blue-500 focus:outline-none",
        ].join(" ")}
        placeholder="z.B. Software, Legal, HR..."
        required
        minLength={1}
        maxLength={50}
      />
    </div>
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-400">
        Farbe
      </label>
      <div className="flex items-center gap-3">
        <input
          type="color"
          value={color}
          onChange={(event) => setColor(event.target.value)}
          className="h-12 w-12 cursor-pointer rounded-lg border-2 border-gray-700 bg-transparent"
        />
        <span
          className="rounded-full px-3 py-1 text-sm font-medium"
          style={{ backgroundColor: `${color}20`, color }}
        >
          {name || "Vorschau"}
        </span>
      </div>
    </div>
  </>
);

interface TagModalProps extends TagFieldsProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: React.FormEventHandler<HTMLFormElement>;
}

export const AddTagModal: React.FC<TagModalProps> = ({
  color,
  isOpen,
  name,
  onClose,
  onSubmit,
  setColor,
  setName,
}) => (
  <ModalFrame isOpen={isOpen} onClose={onClose}>
    <h2 className="mb-4 text-xl font-bold text-white">Neuer Tag</h2>
    <form onSubmit={onSubmit} className="space-y-4">
      <TagFields color={color} name={name} setColor={setColor} setName={setName} />
      <div className="flex gap-3 pt-4">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-500"
        >
          Erstellen
        </button>
      </div>
    </form>
  </ModalFrame>
);

interface EditTagModalProps extends TagModalProps {
  tag: Tag | null;
}

export const EditTagModal: React.FC<EditTagModalProps> = ({
  color,
  isOpen,
  name,
  onClose,
  onSubmit,
  setColor,
  setName,
  tag,
}) => {
  if (!tag) return null;

  return (
    <ModalFrame isOpen={isOpen} onClose={onClose}>
      <h2 className="mb-4 text-xl font-bold text-white">Tag bearbeiten</h2>
      <form onSubmit={onSubmit} className="space-y-4">
        <TagFields color={color} name={name} setColor={setColor} setName={setName} />
        <div className="flex gap-3 pt-4">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-500"
          >
            Speichern
          </button>
        </div>
      </form>
    </ModalFrame>
  );
};
