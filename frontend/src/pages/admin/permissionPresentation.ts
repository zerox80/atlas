export const getPermissionLevelColor = (level: string): string => {
  switch (level) {
    case "full":
      return "text-red-400 bg-red-500/20";
    case "write":
      return "text-yellow-400 bg-yellow-500/20";
    case "read":
      return "text-green-400 bg-green-500/20";
    default:
      return "text-gray-400 bg-gray-500/20";
  }
};

export const getPermissionLevelLabel = (level: string): string => {
  switch (level) {
    case "full":
      return "Vollzugriff";
    case "write":
      return "Bearbeiten";
    case "read":
      return "Nur Lesen";
    default:
      return level;
  }
};
