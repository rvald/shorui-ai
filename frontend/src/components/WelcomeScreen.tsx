import { InputForm } from "./InputForm";

interface WelcomeScreenProps {
  handleSubmit: (submittedInputValue: string, files: File[]) => void;
  onCancel: () => void;
  isLoading: boolean;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  handleSubmit,
  onCancel,
  isLoading,
}) => (
  <div className="h-full flex flex-col items-center justify-center text-center px-4 flex-1 w-full max-w-3xl mx-auto gap-6">
    <div>
      <h1 className="text-5xl md:text-6xl font-semibold text-neutral-100 mb-3">
        HIPAA Compliance Assistant
      </h1>
      <p className="text-xl md:text-2xl text-neutral-400">
        Analyze transcripts, check regulations, and ensure compliance
      </p>
    </div>

    {/* Example Actions */}
    <div className="flex flex-wrap gap-2 justify-center max-w-lg">
      <ExampleChip
        text="📄 Analyze a clinical transcript"
        onClick={() =>
          handleSubmit("I'd like to analyze a clinical transcript for HIPAA compliance. I'll upload the file.", [])
        }
      />
      <ExampleChip
        text="🔍 HIPAA encryption requirements"
        onClick={() =>
          handleSubmit("What does HIPAA require for data encryption?", [])
        }
      />
      <ExampleChip
        text="📋 Check audit logs for PHI"
        onClick={() =>
          handleSubmit("Show me recent PHI detection events from the audit log", [])
        }
      />
    </div>

    <div className="w-full mt-4">
      <InputForm onSubmit={handleSubmit} isLoading={isLoading} onCancel={onCancel} />
    </div>

    <p className="text-xs text-neutral-500">
      Upload clinical transcripts or ask questions about HIPAA regulations
    </p>
  </div>
);

// Example action chip component
function ExampleChip({
  text,
  onClick,
}: {
  text: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-2 text-sm bg-neutral-700 hover:bg-neutral-600 text-neutral-300 rounded-full transition-colors"
    >
      {text}
    </button>
  );
}
