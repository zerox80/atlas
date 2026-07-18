import React from "react";
import { motion } from "framer-motion";
import { FiEdit2, FiPlus, FiTrash2 } from "react-icons/fi";
import type { Tag } from "./types";

interface TagsSectionProps {
  onAddTag: () => void;
  onDeleteTag: (tagId: number) => void;
  onEditTag: (tag: Tag) => void;
  tags: Tag[];
}

const TagsSection: React.FC<TagsSectionProps> = ({
  onAddTag,
  onDeleteTag,
  onEditTag,
  tags,
}) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="space-y-4"
  >
    <div className="flex justify-end">
      <button onClick={onAddTag} className="btn-primary">
        <FiPlus /> Neuer Tag
      </button>
    </div>

    <div className="surface overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-900/50">
          <tr>
            <th className="p-4 text-left font-medium text-gray-400">Farbe</th>
            <th className="p-4 text-left font-medium text-gray-400">Name</th>
            <th className="p-4 text-right font-medium text-gray-400">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {tags.length === 0 ? (
            <tr>
              <td colSpan={3} className="p-8 text-center text-gray-500">
                Keine Tags vorhanden
              </td>
            </tr>
          ) : (
            tags.map((tag) => (
              <tr
                key={tag.id}
                className="border-t border-gray-700 transition-colors hover:bg-gray-800/50"
              >
                <td className="p-4">
                  <div
                    className="h-8 w-8 rounded-lg border-2 border-gray-600"
                    style={{ backgroundColor: tag.color }}
                  />
                </td>
                <td className="p-4">
                  <span
                    className="rounded-full px-3 py-1 text-sm font-medium"
                    style={{ backgroundColor: `${tag.color}20`, color: tag.color }}
                  >
                    {tag.name}
                  </span>
                </td>
                <td className="space-x-2 p-4 text-right">
                  <button
                    onClick={() => onEditTag(tag)}
                    className="rounded p-2 text-blue-400 transition-colors hover:bg-blue-500/20"
                    title="Bearbeiten"
                  >
                    <FiEdit2 />
                  </button>
                  <button
                    onClick={() => onDeleteTag(tag.id)}
                    className="rounded p-2 text-red-400 transition-colors hover:bg-red-500/20"
                    title="Löschen"
                  >
                    <FiTrash2 />
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  </motion.div>
);

export default TagsSection;
