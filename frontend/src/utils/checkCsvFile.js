export const MAX_UPLOAD_BYTES = 1024 * 1024;

export function checkCsvFile(file) {
  if (!file) return "Choose a file.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a .csv file.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than 1 MB.";
  return null;
}
