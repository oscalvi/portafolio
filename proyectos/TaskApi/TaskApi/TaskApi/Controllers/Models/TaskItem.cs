using System.ComponentModel.DataAnnotations;

namespace TaskApi.Models;

public class TaskItem
{
    public int Id { get; set; }

    [Required(ErrorMessage = "The title is required.")]
    [StringLength(200, MinimumLength = 1)]
    public string Title { get; set; } = string.Empty;

    public bool IsCompleted { get; set; }
}
