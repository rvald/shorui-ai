import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Send, StopCircle, Paperclip, X } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";

interface InputFormProps {
  onSubmit: (inputValue: string, files: File[]) => void;
  onCancel: () => void;
  isLoading: boolean;
}

export const InputForm: React.FC<InputFormProps> = ({
  onSubmit,
  onCancel,
  isLoading,
}) => {
  const [internalInputValue, setInternalInputValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleInternalSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!internalInputValue.trim() && files.length === 0) return;
    onSubmit(internalInputValue, files);
    setInternalInputValue("");
    setFiles([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit with Ctrl+Enter (Windows/Linux) or Cmd+Enter (Mac)
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleInternalSubmit();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
    // Reset file input so same file can be selected again if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const removeFile = (indexToRemove: number) => {
    setFiles((prev) => prev.filter((_, index) => index !== indexToRemove));
  };

  const isSubmitDisabled =
    (!internalInputValue.trim() && files.length === 0) || isLoading;

  return (
    <form
      onSubmit={handleInternalSubmit}
      className={`flex flex-col gap-2 p-3 pb-4 max-w-4xl mx-auto w-full`}
    >
      <input
        type="file"
        multiple
        accept="image/*,application/pdf,.txt,text/plain"
        ref={fileInputRef}
        className="hidden"
        onChange={handleFileChange}
      />
      <div
        className={`flex flex-col text-white rounded-3xl rounded-bl-sm rounded-br-sm break-words min-h-7 bg-neutral-700 px-4 pt-3 pb-2`}
      >
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {files.map((file, index) => (
              <div
                key={index}
                className="flex items-center gap-1 bg-neutral-600 rounded-md px-2 py-1 text-xs text-neutral-200"
              >
                <span className="truncate max-w-[150px]">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="text-neutral-400 hover:text-neutral-100"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-row items-center justify-between w-full">
          <Textarea
            value={internalInputValue}
            onChange={(e) => setInternalInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message..."
            className={`w-full text-neutral-100 placeholder-neutral-500 resize-none border-0 focus:outline-none focus:ring-0 outline-none focus-visible:ring-0 shadow-none
                          md:text-base  min-h-[56px] max-h-[200px] bg-transparent`}
            rows={1}
          />
          <div className="-mt-3 flex items-center ">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-neutral-400 hover:text-neutral-100 p-2 cursor-pointer rounded-full transition-all duration-200 mr-1"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
            >
              <Paperclip className="h-5 w-5" />
            </Button>

            {isLoading ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-red-500 hover:text-red-400 hover:bg-red-500/10 p-2 cursor-pointer rounded-full transition-all duration-200"
                onClick={onCancel}
              >
                <StopCircle className="h-5 w-5" />
              </Button>
            ) : (
              <Button
                type="submit"
                variant="ghost"
                className={`${isSubmitDisabled
                  ? "text-neutral-500"
                  : "text-blue-500 hover:text-blue-400 hover:bg-blue-500/10"
                  } p-2 cursor-pointer rounded-full transition-all duration-200 text-base`}
                disabled={isSubmitDisabled}
              >
                <Send className="h-5 w-5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
};
